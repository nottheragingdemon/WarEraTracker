"""Month statements for the Company tax tracker: what each source (owner) country's companies owed a host country in a month,
split into the share handed to conquered regions' original countries and what the host keeps.

Worked out the same way as the Company page: each refresh's wages and the host's tax rates are held until the next refresh
(at most 6 hours) and summed over the month's hours (UTC). On the 1st, last month's statement is frozen in the database
(`statements`), so it no longer changes as the hourly history is thinned and aged out, and it is posted to Discord once.
"""
import bisect
import datetime as dt

CAP_MS = 6 * 3600 * 1000


def _month_bounds(month):
    y, m = int(month[:4]), int(month[5:7])
    a = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
    b = dt.datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=dt.timezone.utc)
    return int(a.timestamp() * 1000), int(b.timestamp() * 1000)


def _step(ts, rows, t):
    """The last row of a time-sorted series (times ts) at or before t."""
    i = bisect.bisect_right(ts, t) - 1
    return rows[i] if i >= 0 else None


def compute(db, host, month, now_ms=None):
    """{owner (partner) country: [tax generated, passed to core countries by the game]} for one host and month (as far as
    tracked). With tax agreements, only partner countries count, and only in the regions their agreement covers (history is
    split by the regions' original country; rows from before that split, 27 Nov 2026, count whole)."""
    from .stages.economy import core_tax_pct
    lo, hi = _month_bounds(month)
    now_ms = now_ms or int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    pct = core_tax_pct(db) / 100
    from .export import company_history
    series = {}   # (owner, core or None for the old rows that did not record it) -> [(t, wages, mgr)]
    split_t = None
    # the same history the Company page uses (all formats merged), unthinned, over the whole stored window
    for r in company_history(db, lambda t, i: i, days=100, full_hours=100 * 24):
        if r[0] != host:
            continue
        core = r[7] if len(r) > 7 else None
        series.setdefault((r[1], core), []).append((r[2], r[5] or 0, r[6] or 0))
        if core is not None:
            split_t = r[2] if split_t is None else min(split_t, r[2])
    # old rows have no core country: estimate the core share from today's split of each owner's pay
    conq_share = {}
    for r in db.execute("""SELECT c.owner_country o, SUM(c.wages+c.mgr) p, SUM(CASE WHEN rn.core IS NOT NULL AND rn.core!=rn.country THEN c.wages+c.mgr ELSE 0 END) q
                           FROM companies c JOIN region_now rn ON rn.region=c.region WHERE rn.country=? GROUP BY c.owner_country""", (host,)):
        conq_share[r["o"]] = (r["q"] / r["p"]) if r["p"] else 0
    rates = [(r["t"], r["income"] or 0, r["manager"] or 0) for r in db.execute("SELECT * FROM rate_hist WHERE country=? ORDER BY t", (host,))]
    rate_ts = [x[0] for x in rates]
    sts = {k: [x[0] for x in s] for k, s in series.items()}
    cur = db.execute("SELECT income, manager FROM country_tax WHERE country=?", (host,)).fetchone()
    runs = [r["t"] for r in db.execute("SELECT t FROM run_log ORDER BY t")]
    from .stages.common import tax_agreements
    ag = tax_agreements(db)
    cover = ag.get(host, {}) if ag is not None else None
    core_of = {r[0]: (r[1] or host) for r in db.execute("SELECT region, core FROM region_now")}
    allowed = {o: (None if regs is None else {core_of.get(x, host) for x in regs}) for o, regs in (cover or {}).items()}
    # rows from before the split count with each owner's split at the first split check (pay share per original country)
    first = {}
    if split_t is not None:
        for (owner, core), s in series.items():
            if core is None:
                continue
            x = _step(sts[(owner, core)], s, split_t + 60_000)
            if x:
                first.setdefault(owner, {})[core] = first.get(owner, {}).get(core, 0) + x[1] + x[2]
    def legacy_shares(owner):
        """(share of the owner's pay that counts, share of it passed on by the game) for rows without the core split"""
        fc = first.get(owner)
        tot = sum(fc.values()) if fc else 0
        if not tot:
            return 1.0, conq_share.get(owner, 0)
        ok = [c for c in fc if cover is None or owner not in allowed or allowed[owner] is None or c in allowed[owner]]
        inc = sum(fc[c] for c in ok)
        return inc / tot, (sum(fc[c] for c in ok if c != host) / inc if inc else 0)
    out = {}
    for i, t0 in enumerate(runs):
        nxt = runs[i + 1] if i + 1 < len(runs) else now_ms
        t1 = min(nxt, t0 + CAP_MS)
        a, b = max(t0, lo), min(t1, hi)   # the part of this check's interval inside the month
        if b <= a:
            continue
        hrs = (b - a) / 3.6e6
        rt = _step(rate_ts, rates, t0)
        ri, rm = (rt[1], rt[2]) if rt else ((cur["income"] or 0, cur["manager"] or 0) if cur else (0, 0))
        for (owner, core), s in series.items():
            if core is None and split_t is not None and t0 >= split_t:
                continue
            if cover is not None and (owner not in cover or (core is not None and allowed[owner] is not None and core not in allowed[owner])):
                continue
            x = _step(sts[(owner, core)], s, t0)
            if not x:
                continue
            tax = (x[1] * ri / 100 + x[2] * rm / 100) * hrs
            if core is None:
                f, share = legacy_shares(owner)
                tax *= f
            else:
                share = 1 if core != host else 0
            o = out.setdefault(owner, [0.0, 0.0])
            o[0] += tax
            o[1] += tax * share * pct
    return {k: [round(v[0], 4), round(v[1], 4)] for k, v in out.items() if v[0] > 0.00005}


def previous_month(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    first = now.replace(day=1)
    return (first - dt.timedelta(days=1)).strftime("%Y-%m")


def freeze(db, hosts, now=None, log=print):
    """On or after the 1st, store last month's statement for each host once (kept permanently)."""
    month = previous_month(now)
    done = {r[0] for r in db.execute("SELECT DISTINCT host FROM statements WHERE month=?", (month,))}
    for h in sorted(set(hosts) - done):
        rows = compute(db, h, month)
        if not rows:
            continue
        db.executemany("INSERT OR REPLACE INTO statements VALUES(?,?,?,?,?)", [(month, h, o, v[0], v[1]) for o, v in rows.items()])
        log(f"statement: {month} frozen for {h} ({len(rows)} source countries)")
    db.commit()
    return month


def preview_text(db, host, month=None):
    """The statement text for a month (default: this one) as it stands now, without saving anything; uses the frozen rows
    when the month is already saved."""
    month = month or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")
    if db.execute("SELECT 1 FROM statements WHERE month=? AND host=?", (month, host)).fetchone():
        return text(db, month, host)
    rows = compute(db, host, month)
    db.executemany("INSERT OR REPLACE INTO statements VALUES(?,?,?,?,?)", [(month, host, o, v[0], v[1]) for o, v in rows.items()])
    try:
        t = text(db, month, host)
    finally:
        db.rollback()
    return t.replace("(final)", "(so far — preview, not final)") if t else None


def text(db, month, host, top=12):
    """A Discord-ready statement for one host and month, from the frozen rows. With tax agreements it is what the host
    sends each partner: the tax it collected on their citizens' companies in the covered regions (after the game's own
    share to a conquered region's original country)."""
    from .stages.common import tax_agreements
    name = lambda c: (db.execute("SELECT name FROM country_tax WHERE country=?", (c,)).fetchone() or [c])[0]
    rows = db.execute("SELECT owner_country o, owed, passed FROM statements WHERE month=? AND host=? ORDER BY owed DESC", (month, host)).fetchall()
    if not rows:
        return None
    label = dt.datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    hn = name(host)
    if tax_agreements(db) is not None:
        lines = [f"🧾 **{hn}: tax agreement payments, {label}** (final)"]
        for r in rows:
            pay = r["owed"] - r["passed"]
            lines.append(f"• {hn} pays **{name(r['o'])}: {pay:,.2f}**" + (f" (tax generated {r['owed']:,.2f}; the game already sent {r['passed']:,.2f} of it to the region's original country)" if r["passed"] >= 0.005 else f" (tax generated {r['owed']:,.2f})"))
        lines.append(f"**Total {hn} pays: {sum(r['owed'] - r['passed'] for r in rows):,.2f}**")
        lines.append("Employee and manager income tax on the partners' citizens' companies in the regions each agreement covers, every hour of the month (UTC).")
        return "\n".join(lines)
    tot = sum(r["owed"] for r in rows)
    pas = sum(r["passed"] for r in rows)
    lines = [f"🧾 **{name(host)}: company tax statement, {label}** (final)"]
    for r in rows[:top]:
        lines.append(f"• {name(r['o'])}: {r['owed']:,.2f}" + (f" (to core {r['passed']:,.2f})" if r["passed"] >= 0.005 else ""))
    if len(rows) > top:
        rest = rows[top:]
        lines.append(f"• {len(rest)} more countries: {sum(r['owed'] for r in rest):,.2f}")
    lines.append(f"**Total owed: {tot:,.2f}**" + (f" · to core countries {pas:,.2f} · {name(host)} keeps {tot - pas:,.2f}" if pas >= 0.005 else ""))
    lines.append("Tracked wages × the host's tax rates for every hour of the month (UTC). Payments already made aren't subtracted.")
    return "\n".join(lines)
