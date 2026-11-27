"""Regions, country taxes and income, and the companies of the alliance's citizens."""
import os
import json, datetime as dt

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
        db.execute("INSERT OR REPLACE INTO region_now VALUES(?,?,?,?,?,?,?,?)",
                   (r["_id"], r.get("name") or r.get("code"), r.get("country"), float(inc.get("employeeIncomeTax") or 0),
                    float(inc.get("managerIncomeTax") or 0), float(inc.get("strategicResourcesBonus") or 0),
                    r.get("companyCount") or 0, r.get("employeeCount") or 0))
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
    """Per (region, owner country): active companies, workers and wages/h at this check; a row is written only when it changed."""
    import time
    now = int(time.time() * 1000)
    agg = {}
    for r in rows:  # (id,name,owner,item,value,region,owner_country,seen,workers,wages)
        if not r[5] or not r[6]:
            continue
        a = agg.setdefault((r[5], r[6]), [0, 0, 0.0, 0.0]); a[0] += 1; a[1] += r[8]; a[2] += r[9]; a[3] += r[10]
    last = {(x["region"], x["owner_country"]): (x["companies"], x["workers"], x["wages"], x["mgr"] or 0.0) for x in db.execute(
        "SELECT region,owner_country,companies,workers,wages,mgr FROM wage_snap WHERE (region,owner_country,t) IN "
        "(SELECT region,owner_country,MAX(t) FROM wage_snap GROUP BY region,owner_country)")}
    for k in set(agg) | set(last):
        cur = agg.get(k) or (0, 0, 0.0, 0.0)
        prev = last.get(k)
        if prev is None and cur == (0, 0, 0.0, 0.0):
            continue
        if prev is None or prev[0] != cur[0] or prev[1] != cur[1] or abs(prev[2] - cur[2]) > 1e-9 or abs(prev[3] - cur[3]) > 1e-9:
            db.execute("INSERT OR REPLACE INTO wage_snap VALUES(?,?,?,?,?,?,?)", (k[0], k[1], now, cur[0], cur[1], round(cur[2], 6), round(cur[3], 6)))


def collect_companies(c, db, scope):
    """Citizens of the scope's member countries and the companies they own (small: ~1k citizens), with the region each stands in."""
    if not scope or not scope.members:
        log("companies: no alliance scope, skipped"); return
    ts = now_iso()
    citizens = {}
    members = list(scope.members)
    for country, users in zip(members, c.map(lambda k: list(c.pages("user.getUsersByCountry", countryId=k, limit=100)), members)):
        for u in users:
            citizens[u["_id"]] = country
    log(f"companies: {len(citizens)} citizens in {len(scope.members)} countries")
    known = {r["id"] for r in db.execute("SELECT id FROM users WHERE name IS NOT NULL")}
    need = [u for u in citizens if u not in known]
    for u, d in c.lookup_users(need).items():
        db.execute("INSERT INTO users(id,country,mu,name) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET country=excluded.country, name=excluded.name",
                   (u, d.get("country") or citizens[u], d.get("mu"), d.get("username")))
        db.execute("INSERT OR REPLACE INTO names VALUES('user',?,?,NULL)", (u, d.get("username")))
    db.commit()
    owned, pending = {}, [(u, None) for u in citizens]
    while pending:
        chunks = [pending[i:i + 40] for i in range(0, min(len(pending), 320), 40)]   # up to 8 batch requests in flight
        pending = pending[320:]
        results = c.batch_many([[("company.getCompanies", {"userId": u, "perPage": 100, "cursor": cur}) for u, cur in ch] for ch in chunks])
        for chunk, res in zip(chunks, results):
            for (u, _), d in zip(chunk, res):
                if not d:
                    continue
                for cid in d["items"]:
                    owned[cid] = u
                if d.get("nextCursor") and d["items"]:
                    pending.append((u, d["nextCursor"]))
    # only companies hosted in this country are kept (the company tax tracker's host); "" or "all" keeps every host
    host = os.environ.get("WARTRACK_HOST", "Ireland").strip()
    host_regions = None
    if host and host.lower() != "all":
        hid = [r["country"] for r in db.execute("SELECT country FROM country_tax WHERE lower(name)=lower(?)", (host,))]
        host_regions = {r["region"] for r in db.execute("SELECT region FROM region_now WHERE country=?", (hid[0],))} if hid else None
        log(f"companies: keeping only those hosted in {host}" + ("" if host_regions else " (host not found: keeping all)"))
    seen = {r["id"]: r["seen"] or "" for r in db.execute("SELECT id,seen FROM companies")}
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat(timespec="seconds")
    skip = {r["id"] for r in db.execute("SELECT id FROM company_skip WHERE checked>=?", (cutoff,))} if host_regions else set()
    ids = sorted((x for x in owned if x not in skip), key=lambda x: seen.get(x, ""))   # never-seen first, then the stalest: each run refreshes what fits the budget
    rows = []
    import time as _t
    t0, est_ok = _t.monotonic(), True
    BUDGET = float(os.environ.get("WARTRACK_COMPANY_BUDGET", "480"))
    log(f"companies: {len(ids)} owned, fetching details")
    GROUP = 320   # ids per round: 8 batch requests of 40 in flight at once
    for i in range(0, len(ids), GROUP):
        group = ids[i:i + GROUP]
        log(f"  companies {i}/{len(ids)} ({_t.monotonic() - t0:.0f}s, api calls so far: {c.n})")
        if _t.monotonic() - t0 > BUDGET:   # keep each run short; the remaining companies keep their last values and go first next run
            log(f"  companies: time budget used after {i}/{len(ids)}; the rest are refreshed in the next runs")
            break
        chunks = [group[k:k + 40] for k in range(0, len(group), 40)]
        details = [d for res in c.batch_many([[("company.getById", {"companyId": x}) for x in ch] for ch in chunks]) for d in res]
        if host_regions:   # other hosts are remembered for a week so they are not fetched again every run
            db.executemany("INSERT OR REPLACE INTO company_skip VALUES(?,?)", [(cid, ts) for cid, d in zip(group, details) if d and d.get("region") not in host_regions])
        active = [(cid, d) for cid, d in zip(group, details) if d and not d.get("disabledAt") and (host_regions is None or d.get("region") in host_regions)]  # inactive companies pay no wages
        # live hourly money cost of the real employees and the manager (not lagged, not cached)
        est = []
        if active and est_ok:
            ech = [active[k:k + 40] for k in range(0, len(active), 40)]
            est = [e for res in c.batch_many([[("employee.getCompanyEstimate", {"companyId": cid}) for cid, _ in ch] for ch in ech], official=True) for e in res]
        est = est or [None] * len(active)
        # the company record no longer lists its workers: their list (with each wage) comes from employee.getCompanyEmployees
        staff = [None] * len(active)
        if active:
            ech = [active[k:k + 40] for k in range(0, len(active), 40)]
            staff = [x for res in c.batch_many([[("employee.getCompanyEmployees", {"companyId": cid}) for cid, _ in ch] for ch in ech], official=True) for x in res]
        for (cid, d), e, sl in zip(active, est, staff):
            ws = sl if isinstance(sl, list) else (d.get("workers") or [])
            if e:
                wages, mgr = float(e.get("wageCost") or 0), float(e.get("managerCost") or 0)
            else:  # estimate unavailable: fall back to the wages of the listed employees
                wages, mgr = sum(float(w.get("wage") or 0) for w in ws), 0.0
            rows.append((cid, d.get("name"), d.get("user") or owned[cid], d.get("itemCode"), d.get("estimatedValue") or 0,
                         d.get("region"), citizens.get(owned[cid]), ts, len(ws), round(wages, 6), round(mgr, 6)))
    if ids:
        db.executemany("DELETE FROM companies WHERE id=?", [(r["id"],) for r in db.execute("SELECT id FROM companies").fetchall() if r["id"] not in owned])
    else:
        db.execute("DELETE FROM companies")
    if host_regions:
        db.executemany("DELETE FROM companies WHERE id=?", [(r["id"],) for r in db.execute("SELECT id,region FROM companies").fetchall() if r["region"] not in host_regions])
    db.executemany("INSERT OR REPLACE INTO companies(id,name,owner,item,value,region,owner_country,seen,workers,wages,mgr) VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
    allrows = [tuple(r) for r in db.execute("SELECT id,name,owner,item,value,region,owner_country,seen,workers,wages,mgr FROM companies")]
    snapshot_wages(db, allrows)
    db.commit()
    log(f"companies: {len(rows)} refreshed this run, {len(allrows)} stored")
