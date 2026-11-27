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
    """{owner country: [tax owed, passed to core countries]} for one host and month (as far as tracked)."""
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
            x = _step(sts[(owner, core)], s, t0)
            if not x:
                continue
            tax = (x[1] * ri / 100 + x[2] * rm / 100) * hrs
            share = conq_share.get(owner, 0) if core is None else (1 if core != host else 0)
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
    """A Discord-ready statement for one host and month, from the frozen rows."""
    name = lambda c: (db.execute("SELECT name FROM country_tax WHERE country=?", (c,)).fetchone() or [c])[0]
    rows = db.execute("SELECT owner_country o, owed, passed FROM statements WHERE month=? AND host=? ORDER BY owed DESC", (month, host)).fetchall()
    if not rows:
        return None
    tot = sum(r["owed"] for r in rows)
    pas = sum(r["passed"] for r in rows)
    label = dt.datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    lines = [f"🧾 **{name(host)}: company tax statement, {label}** (final)"]
    for r in rows[:top]:
        lines.append(f"• {name(r['o'])}: {r['owed']:,.2f}" + (f" (to core {r['passed']:,.2f})" if r["passed"] >= 0.005 else ""))
    if len(rows) > top:
        rest = rows[top:]
        lines.append(f"• {len(rest)} more countries: {sum(r['owed'] for r in rest):,.2f}")
    lines.append(f"**Total owed: {tot:,.2f}**" + (f" · to core countries {pas:,.2f} · {name(host)} keeps {tot - pas:,.2f}" if pas >= 0.005 else ""))
    lines.append("Tracked wages × the host's tax rates for every hour of the month (UTC). Payments already made aren't subtracted.")
    return "\n".join(lines)
