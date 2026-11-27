"""Regions, country taxes and income, and the companies of the alliance's citizens."""
import os
import json

from .common import alliance_countries, log, now_iso


def collect_regions(c, db):
    """Region names (one public call) so battles can show where they are fought."""
    d = c.call("region.getRegionsObject")
    for r in d.values():
        db.execute("INSERT OR REPLACE INTO names VALUES('region',?,?,?)", (r["_id"], r.get("name") or r.get("code"), r.get("country")))
    # tax-rate history: remember each check time and store a region's hourly tax whenever it changes
    now = int(__import__("time").time() * 1000)
    last = {r["region"]: (r["emp"], r["mgr"]) for r in db.execute(
        "SELECT region,emp,mgr FROM region_rate WHERE (region,t) IN (SELECT region,MAX(t) FROM region_rate GROUP BY region)")}
    db.execute("INSERT OR IGNORE INTO run_log VALUES(?)", (now,))
    changed = 0
    for r in d.values():
        inc = r.get("income") or {}
        cur = (float(inc.get("employeeIncomeTax") or 0), float(inc.get("managerIncomeTax") or 0))
        if last.get(r["_id"]) != cur:
            db.execute("INSERT OR REPLACE INTO region_rate VALUES(?,?,?,?)", (r["_id"], now, cur[0], cur[1])); changed += 1
    db.execute("DELETE FROM region_now")
    for r in d.values():
        inc = r.get("income") or {}
        db.execute("INSERT OR REPLACE INTO region_now(region,name,country,emp,mgr,res,companies,employees,core) VALUES(?,?,?,?,?,?,?,?,?)",
                   (r["_id"], r.get("name") or r.get("code"), r.get("country"), float(inc.get("employeeIncomeTax") or 0),
                    float(inc.get("managerIncomeTax") or 0), float(inc.get("strategicResourcesBonus") or 0),
                    r.get("companyCount") or 0, r.get("employeeCount") or 0, r.get("initialCountry") or r.get("country")))
    try:   # share of a conquered region's tax the game hands to the region's original country
        pct = ((c.call("gameConfig.getGameConfig") or {}).get("country") or {}).get("conqueredRegionCoreTaxPercent")
        if isinstance(pct, (int, float)):
            db.execute("INSERT OR REPLACE INTO meta VALUES('core_tax_pct',?)", (str(pct),))
    except Exception as e:
        log(f"game config: skipped ({e})")
    try:
        lastr = {r["country"]: (r["income"], r["manager"]) for r in db.execute(
            "SELECT country,income,manager FROM rate_hist WHERE (country,t) IN (SELECT country,MAX(t) FROM rate_hist GROUP BY country)")}
        tracked = alliance_countries(db)
        for ct in c.call("country.getAllCountries"):
            tx = ct.get("taxes") or {}
            cur = (tx.get("income"), tx.get("manager"))
            if lastr.get(ct["_id"]) != cur:
                db.execute("INSERT OR REPLACE INTO rate_hist VALUES(?,?,?,?)", (ct["_id"], now, cur[0], cur[1]))
            db.execute("INSERT OR REPLACE INTO country_tax VALUES(?,?,?,?,?)",
                       (ct["_id"], ct.get("name"), tx.get("income"), tx.get("manager"), tx.get("market")))
            cw = (ct.get("rankings") or {}).get("countryWealth") or {}
            if ct["_id"] in tracked and isinstance(ct.get("income"), dict):   # hourly history for the alliance's countries
                db.execute("INSERT OR REPLACE INTO country_income VALUES(?,?,?,?)",
                           (ct["_id"], now - now % 3_600_000, ct.get("money"), json.dumps(ct["income"], separators=(",", ":"))))
            db.execute("""INSERT OR REPLACE INTO country_now(country,name,money,wealth,wealth_rank,population,development,updated,income)
                          VALUES(?,?,?,?,?,?,?,?,?)""",
                       (ct["_id"], ct.get("name"), ct.get("money"), cw.get("value"), cw.get("rank"),
                        ct.get("currentPopulation"), ct.get("currentDevelopment"), now_iso(),
                        json.dumps(ct["income"], separators=(",", ":")) if isinstance(ct.get("income"), dict) else None))
    except Exception as e:
        log(f"country taxes: skipped ({e})")
    db.commit()
    log(f"regions: {len(d)} stored, tax rates changed in {changed}")


def snapshot_wages(db, rows):
    """Per (host country, region's core country, owner country): active companies, workers, wages/h and manager pay/h at this check. A row is
    written only when something changed by more than 0.5% (or the company or worker count changed), to keep history small."""
    import time
    now = int(time.time() * 1000)
    host_of = {r["region"]: (r["country"], r["core"] or r["country"]) for r in db.execute("SELECT region, country, core FROM region_now")}
    agg = {}
    for r in rows:  # (id,name,owner,item,value,region,owner_country,seen,workers,wages,mgr)
        hc = host_of.get(r[5])
        if not hc or not r[6]:
            continue
        a = agg.setdefault((hc[0], hc[1], r[6]), [0, 0, 0.0, 0.0]); a[0] += 1; a[1] += r[8] or 0; a[2] += r[9] or 0; a[3] += r[10] or 0
    last = {(x["host"], x["core"], x["owner_country"]): (x["companies"], x["workers"], x["wages"], x["mgr"] or 0.0) for x in db.execute(
        "SELECT host,core,owner_country,companies,workers,wages,mgr FROM wage_snap3 WHERE (host,core,owner_country,t) IN "
        "(SELECT host,core,owner_country,MAX(t) FROM wage_snap3 GROUP BY host,core,owner_country)")}
    _write_changes(db, "wage_snap3", agg, last, now)
    # conquered regions also per region (few of them), so one region's split history is exact
    hosts = {hc[0] for hc in agg}
    conq = {reg for reg, hc in host_of.items() if hc[0] != hc[1] and hc[0] in hosts}
    ragg = {}
    for r in rows:
        if r[5] in conq and r[6]:
            a = ragg.setdefault((r[5], r[6]), [0, 0, 0.0, 0.0]); a[0] += 1; a[1] += r[8] or 0; a[2] += r[9] or 0; a[3] += r[10] or 0
    rlast = {(x["region"], x["owner_country"]): (x["companies"], x["workers"], x["wages"], x["mgr"] or 0.0) for x in db.execute(
        "SELECT region,owner_country,companies,workers,wages,mgr FROM wage_snap_reg WHERE (region,owner_country,t) IN "
        "(SELECT region,owner_country,MAX(t) FROM wage_snap_reg GROUP BY region,owner_country)")}
    rlast = {k: v for k, v in rlast.items() if k[0] in conq or v != (0, 0, 0.0, 0.0)}
    _write_changes(db, "wage_snap_reg", ragg, rlast, now)


def _write_changes(db, table, agg, last, now):
    """Write a snapshot row per key whose counts changed or whose pay moved by more than 0.5% since its last row."""
    moved = lambda a, b: abs(a - b) > max(1e-9, 0.005 * max(abs(a), abs(b)))
    for k in set(agg) | set(last):
        cur = tuple(agg.get(k) or (0, 0, 0.0, 0.0))
        prev = last.get(k)
        if prev is None and cur == (0, 0, 0.0, 0.0):
            continue
        if prev is None or prev[0] != cur[0] or prev[1] != cur[1] or moved(prev[2], cur[2]) or moved(prev[3], cur[3]):
            db.execute(f"INSERT OR REPLACE INTO {table} VALUES({','.join('?' * (len(k) + 5))})", (*k, now, cur[0], cur[1], round(cur[2], 6), round(cur[3], 6)))


def collect_company_index(c, db, scope, recheck_days=30, budget=None):
    """Where every company in the game stands. The API can only list all companies together (newest first, hundreds of
    thousands including closed ones), so each daily run:
      1. reads the top of the list until it reaches companies it already knows (new companies);
      2. continues the full list from where the last run stopped, for part of its time; when a full pass ends, companies
         that weren't seen in it are dropped as gone (never before a pass is complete);
      3. looks up where the not-yet-located companies stand, then re-checks the oldest 1/recheck_days of the companies
         outside alliance countries (those inside are re-checked hourly by the companies stage), to catch moves in.
    The hourly companies stage then refreshes those standing in alliance countries."""
    import time as _t
    budget = float(budget or os.environ.get("WARTRACK_INDEX_BUDGET", "1500"))
    t0, ts = _t.monotonic(), now_iso()
    meta = lambda k: (db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone() or [None])[0]
    setm = lambda k, v: db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, v))
    known = {r[0] for r in db.execute("SELECT id FROM company_loc")}
    cursor = meta("index_cursor")
    if not cursor:   # a new full pass starts
        setm("index_pass", str(int(meta("index_pass") or 0) + 1))
    pass_no = int(meta("index_pass") or 1)

    def remember(ids_):
        db.executemany("INSERT INTO company_loc(id, listed) VALUES(?, ?) ON CONFLICT(id) DO UPDATE SET listed=excluded.listed", [(x, pass_no) for x in ids_])
    # 1. new companies at the top of the list
    new, run_known, cur = 0, 0, None
    for _ in range(300):
        d = c.call("company.getCompanies", perPage=100, cursor=cur)
        items = d.get("items") or []
        fresh = [x for x in items if x not in known]
        new += len(fresh); remember(items); known.update(items)
        run_known = 0 if fresh else run_known + len(items)
        cur = d.get("nextCursor")
        if not cur or not items or run_known >= 2000:
            break
    # 2. the full pass, resumed
    listed, finished = 0, False
    while _t.monotonic() - t0 < budget * 0.45:
        d = c.call("company.getCompanies", perPage=100, cursor=cursor)
        items = d.get("items") or []
        remember(items); known.update(items); listed += len(items)
        cursor = d.get("nextCursor")
        if not cursor or not items:
            finished = True; break
        if listed % 20000 == 0:
            log(f"  company index: full pass {pass_no}, {listed} listed this run ({_t.monotonic() - t0:.0f}s)")
    gone = 0
    if finished:
        gone_ids = [r[0] for r in db.execute("SELECT id FROM company_loc WHERE listed IS NULL OR listed < ?", (pass_no,))]
        for i in range(0, len(gone_ids), 500):
            ch = gone_ids[i:i + 500]; ph = ",".join("?" * len(ch))
            db.execute(f"DELETE FROM company_loc WHERE id IN ({ph})", ch)
            db.execute(f"DELETE FROM companies WHERE id IN ({ph})", ch)
        gone = len(gone_ids)
        setm("index_cursor", ""); setm("index_full_at", ts)
    else:
        setm("index_cursor", cursor or "")
    db.commit()
    # 3. locate: unknown first (newest first), then the stalest re-checks
    unknown = [r[0] for r in db.execute("SELECT id FROM company_loc WHERE region IS NULL AND checked IS NULL ORDER BY rowid DESC")]
    # re-checks: companies in alliance countries are re-checked every hour by the companies stage, so here only the others,
    # to catch one moving into an alliance country: 1/recheck_days of them a day, oldest first (closed ones are skipped)
    hosts_ = alliance_countries(db) or set(scope.members if scope and scope.members else [])
    host_regions_ = {r[0] for r in db.execute(f"SELECT region FROM region_now WHERE country IN ({','.join('?' * len(hosts_))})", list(hosts_))} if hosts_ else set()
    others = [r[0] for r in db.execute("SELECT id, region FROM company_loc WHERE checked IS NOT NULL AND disabled=0 ORDER BY checked") if r[1] not in host_regions_]
    stale = others[:max(1, len(others) // recheck_days)]
    todo, done = unknown + stale, 0
    for g in range(0, len(todo), 320):
        if _t.monotonic() - t0 > budget:
            break
        group = todo[g:g + 320]
        res = c.batch_many([[("company.getById", {"companyId": x}) for x in group[k:k + 40]] for k in range(0, len(group), 40)])
        for x, d in zip(group, (d for r in res for d in r)):
            if d:
                db.execute("UPDATE company_loc SET region=?, owner=?, disabled=?, checked=? WHERE id=?",
                           (d.get("region"), d.get("user"), 1 if d.get("disabledAt") else 0, ts, x))
            else:   # not found: closed
                db.execute("UPDATE company_loc SET disabled=1, checked=? WHERE id=?", (ts, x))
        done += len(group)
        db.commit()
    # owners of companies in the alliance's countries: refresh their citizenship once a day
    hosts = alliance_countries(db) or set(scope.members if scope and scope.members else [])
    if hosts:
        ph = ",".join("?" * len(hosts))
        owners = [r[0] for r in db.execute(f"SELECT DISTINCT l.owner FROM company_loc l JOIN region_now r ON r.region=l.region WHERE r.country IN ({ph}) AND l.disabled=0", list(hosts))]
        _store_owners(c, db, owners)
    db.commit()
    left = db.execute("SELECT COUNT(*) FROM company_loc WHERE checked IS NULL").fetchone()[0]
    log(f"company index: {new} new at the top; full pass {pass_no} {'finished' if finished else 'continues next run'} ({listed} listed this run, "
        f"{gone} gone); {min(done, len(unknown))} located, {max(0, done - len(unknown))} re-checked, {left} still to locate; "
        f"{db.execute('SELECT COUNT(*) FROM company_loc').fetchone()[0]} known")


def _store_owners(c, db, owners):
    for u, d in c.lookup_users(owners).items():
        db.execute("INSERT INTO users(id,country,mu,name) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET country=excluded.country, mu=excluded.mu, name=excluded.name",
                   (u, d.get("country"), d.get("mu"), d.get("username")))
        db.execute("INSERT OR REPLACE INTO names VALUES('user',?,?,NULL)", (u, d.get("username")))


def core_tax_pct(db):
    """The share (%) of a conquered region's tax the game hands to its original country (game config; 10 if unknown)."""
    try:
        return float((db.execute("SELECT v FROM meta WHERE k='core_tax_pct'").fetchone() or ["10"])[0])
    except (TypeError, ValueError):
        return 10.0


def coverage_rows(db, hosts):
    """Per host country: [host, companies tracked, staffed, workers, wage tax/h (all owners), game companies, game workers, game tax/h,
    staffed companies whose storage is full, wage tax/h leaving those out]. A full company stops producing; whether the game still
    taxes its wages is what the full_hist record (hourly) is meant to show."""
    rate = {r["country"]: (r["income"] or 0, r["manager"] or 0) for r in db.execute("SELECT country, income, manager FROM country_tax")}
    keep = 1 - core_tax_pct(db) / 100   # a conquered region's game tax figure is what the holder keeps: gross it up to compare
    out = []
    for h in sorted(hosts):
        g = db.execute("""SELECT COALESCE(SUM(companies),0) co, COALESCE(SUM(employees),0) em,
            COALESCE(SUM((COALESCE(emp,0)+COALESCE(mgr,0)) / CASE WHEN core IS NOT NULL AND core!=country THEN ? ELSE 1 END),0) tax
            FROM region_now WHERE country=?""", (keep, h)).fetchone()
        t = db.execute("""SELECT COUNT(*) n, COALESCE(SUM(c.workers>0),0) staffed, COALESCE(SUM(c.workers),0) w, COALESCE(SUM(c.wages),0) wg, COALESCE(SUM(c.mgr),0) mg,
            COALESCE(SUM(c.workers>0 AND c.full=1),0) fs, COALESCE(SUM(CASE WHEN c.full=1 THEN 0 ELSE c.wages END),0) wgn,
            COALESCE(SUM(CASE WHEN c.full=1 THEN 0 ELSE c.mgr END),0) mgn
            FROM companies c JOIN region_now r ON r.region=c.region WHERE r.country=?""", (h,)).fetchone()
        ri, rm = rate.get(h, (0, 0))
        out.append([h, t["n"], t["staffed"], t["w"], round(t["wg"] * ri / 100 + t["mg"] * rm / 100, 3), g["co"], g["em"], round(g["tax"], 3),
                    t["fs"], round(t["wgn"] * ri / 100 + t["mgn"] * rm / 100, 3)])
    return out


def collect_companies(c, db, scope):
    """Every company standing in an alliance country (the hosts), whoever owns it: details, the live wage estimate and the
    employee list. Located by the daily company index; stalest first within a time budget."""
    import time as _t
    hosts = alliance_countries(db) or set(scope.members if scope and scope.members else [])
    if not hosts:
        log("companies: no alliance countries, skipped"); return
    ph = ",".join("?" * len(hosts))
    host_regions = {r[0] for r in db.execute(f"SELECT region FROM region_now WHERE country IN ({ph})", list(hosts))}
    cand = {r["id"]: r["owner"] for r in db.execute("SELECT id, owner, region FROM company_loc WHERE disabled=0") if r["region"] in host_regions}
    if not cand:
        log("companies: the company index is empty; run the Company index workflow once"); return
    ts = now_iso()
    seen = {r["id"]: r["seen"] or "" for r in db.execute("SELECT id,seen FROM companies")}
    ids = sorted(cand, key=lambda x: seen.get(x, ""))   # never-seen first, then the stalest
    owner_country = {r["id"]: r["country"] for r in db.execute("SELECT id, country FROM users")}
    unknown = [o for o in set(cand.values()) if o and not owner_country.get(o)]
    if unknown:
        _store_owners(c, db, unknown)
        owner_country = {r["id"]: r["country"] for r in db.execute("SELECT id, country FROM users")}
    t0, rows = _t.monotonic(), []
    BUDGET = float(os.environ.get("WARTRACK_COMPANY_BUDGET", "480"))
    log(f"companies: {len(ids)} in {len(hosts)} alliance countries, fetching details")
    for i in range(0, len(ids), 320):   # 8 batch requests of 40 in flight at once
        if _t.monotonic() - t0 > BUDGET:
            log(f"  companies: time budget used after {i}/{len(ids)}; the rest are refreshed in the next runs"); break
        if i and i % 1600 == 0:
            log(f"  companies {i}/{len(ids)} ({_t.monotonic() - t0:.0f}s, api calls so far: {c.n})")
        group = ids[i:i + 320]
        chunks = [group[k:k + 40] for k in range(0, len(group), 40)]
        details = [d for res in c.batch_many([[("company.getById", {"companyId": x}) for x in ch] for ch in chunks]) for d in res]
        for cid, d in zip(group, details):   # keep the index current: moved, closed or disabled
            if d:
                db.execute("UPDATE company_loc SET region=?, owner=?, disabled=?, checked=? WHERE id=?", (d.get("region"), d.get("user"), 1 if d.get("disabledAt") else 0, ts, cid))
        active = [(cid, d) for cid, d in zip(group, details) if d and not d.get("disabledAt") and d.get("region") in host_regions]
        ech = [active[k:k + 40] for k in range(0, len(active), 40)]
        est = [e for res in c.batch_many([[("employee.getCompanyEstimate", {"companyId": cid}) for cid, _ in ch] for ch in ech], official=True) for e in res] if active else []
        staff = [x for res in c.batch_many([[("employee.getCompanyEmployees", {"companyId": cid}) for cid, _ in ch] for ch in ech], official=True) for x in res] if active else []
        for (cid, d), e, sl in zip(active, est or [None] * len(active), staff or [None] * len(active)):
            ws = sl if isinstance(sl, list) else []
            if e:
                wages, mgr = float(e.get("wageCost") or 0), float(e.get("managerCost") or 0)
            else:   # estimate unavailable: the wages of the listed employees
                wages, mgr = sum(float(w.get("wage") or 0) for w in ws), 0.0
            owner = d.get("user") or cand.get(cid)
            rows.append((cid, d.get("name"), owner, d.get("itemCode"), d.get("estimatedValue") or 0,
                         d.get("region"), owner_country.get(owner), ts, len(ws), round(wages, 6), round(mgr, 6), 1 if d.get("isFull") else 0))
    # drop companies that left the alliance's countries, closed or disappeared from the index
    keep = {r["id"] for r in db.execute("SELECT id, region FROM company_loc WHERE disabled=0") if r["region"] in host_regions}
    db.executemany("DELETE FROM companies WHERE id=?", [(r["id"],) for r in db.execute("SELECT id FROM companies").fetchall() if r["id"] not in keep])
    db.executemany("INSERT OR REPLACE INTO companies(id,name,owner,item,value,region,owner_country,seen,workers,wages,mgr,full) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    allrows = [tuple(r) for r in db.execute("SELECT id,name,owner,item,value,region,owner_country,seen,workers,wages,mgr FROM companies")]
    snapshot_wages(db, allrows)
    day = ts[:10]   # coverage against the game's own figures, the latest check of each day (Status page trend)
    now_ms = int(_t.time() * 1000)
    for r in coverage_rows(db, hosts):
        db.execute("INSERT OR REPLACE INTO coverage_hist VALUES(?,?,?,?,?,?,?,?)", (day, r[0], r[2], r[5], r[3], r[6], r[4], r[7]))
        db.execute("INSERT OR REPLACE INTO full_hist VALUES(?,?,?,?,?,?,?)", (r[0], now_ms, r[2], r[8], r[4], r[9], r[7]))
    db.commit()
    log(f"companies: {len(rows)} refreshed this run, {len(allrows)} stored")
