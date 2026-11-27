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
    """Per (host country, owner country): active companies, workers, wages/h and manager pay/h at this check. A row is
    written only when something changed by more than 0.5% (or the company or worker count changed), to keep history small."""
    import time
    now = int(time.time() * 1000)
    host_of = {r["region"]: r["country"] for r in db.execute("SELECT region, country FROM region_now")}
    agg = {}
    for r in rows:  # (id,name,owner,item,value,region,owner_country,seen,workers,wages,mgr)
        h = host_of.get(r[5])
        if not h or not r[6]:
            continue
        a = agg.setdefault((h, r[6]), [0, 0, 0.0, 0.0]); a[0] += 1; a[1] += r[8] or 0; a[2] += r[9] or 0; a[3] += r[10] or 0
    last = {(x["host"], x["owner_country"]): (x["companies"], x["workers"], x["wages"], x["mgr"] or 0.0) for x in db.execute(
        "SELECT host,owner_country,companies,workers,wages,mgr FROM wage_snap2 WHERE (host,owner_country,t) IN "
        "(SELECT host,owner_country,MAX(t) FROM wage_snap2 GROUP BY host,owner_country)")}
    moved = lambda a, b: abs(a - b) > max(1e-9, 0.005 * max(abs(a), abs(b)))
    for k in set(agg) | set(last):
        cur = tuple(agg.get(k) or (0, 0, 0.0, 0.0))
        prev = last.get(k)
        if prev is None and cur == (0, 0, 0.0, 0.0):
            continue
        if prev is None or prev[0] != cur[0] or prev[1] != cur[1] or moved(prev[2], cur[2]) or moved(prev[3], cur[3]):
            db.execute("INSERT OR REPLACE INTO wage_snap2 VALUES(?,?,?,?,?,?,?)", (k[0], k[1], now, cur[0], cur[1], round(cur[2], 6), round(cur[3], 6)))


def collect_company_index(c, db, scope, recheck_days=7, budget=None):
    """Where every company in the game stands. The API can only list companies all together (or by owner), so this reads the
    whole list of ids (about 1,100 pages), looks up new ones, and re-checks the oldest 1/recheck_days of the rest, so moves
    and closures are caught within a week. Run daily; the hourly companies stage then refreshes those in alliance countries."""
    import time as _t
    budget = float(budget or os.environ.get("WARTRACK_INDEX_BUDGET", "1500"))
    t0, ts = _t.monotonic(), now_iso()
    ids, complete = [], True
    for n, cid in enumerate(c.pages("company.getCompanies", max_pages=3000, perPage=100), 1):
        ids.append(cid)
        if n % 20000 == 0:
            log(f"  company index: {n} ids listed ({_t.monotonic() - t0:.0f}s)")
        if _t.monotonic() - t0 > budget / 2:
            complete = False; break
    seen = set(ids)
    known = {r["id"]: r["checked"] or "" for r in db.execute("SELECT id, checked FROM company_loc")}
    gone = [k for k in known if k not in seen] if complete else []
    for i in range(0, len(gone), 500):
        ch = gone[i:i + 500]; ph = ",".join("?" * len(ch))
        db.execute(f"DELETE FROM company_loc WHERE id IN ({ph})", ch)
        db.execute(f"DELETE FROM companies WHERE id IN ({ph})", ch)
    new = [x for x in ids if x not in known]
    stale = sorted((k for k in known if k in seen), key=lambda k: known[k])[:max(1, len(known) // recheck_days)] if known else []
    todo = new + stale
    done = 0
    for g in range(0, len(todo), 320):
        if _t.monotonic() - t0 > budget:
            log(f"  company index: time budget used; {len(todo) - done} lookups left for the next run"); break
        group = todo[g:g + 320]
        res = c.batch_many([[("company.getById", {"companyId": x}) for x in group[k:k + 40]] for k in range(0, len(group), 40)])
        for x, d in zip(group, (d for r in res for d in r)):
            if d:
                db.execute("INSERT OR REPLACE INTO company_loc VALUES(?,?,?,?,?)", (x, d.get("region"), d.get("user"), 1 if d.get("disabledAt") else 0, ts))
        done += len(group)
        db.commit()
    # owners of companies in the alliance's countries: refresh their citizenship once a day
    hosts = alliance_countries(db) or set(scope.members if scope and scope.members else [])
    if hosts:
        ph = ",".join("?" * len(hosts))
        owners = [r[0] for r in db.execute(f"SELECT DISTINCT l.owner FROM company_loc l JOIN region_now r ON r.region=l.region WHERE r.country IN ({ph})", list(hosts))]
        _store_owners(c, db, owners)
    db.commit()
    log(f"company index: {len(ids)} companies listed{'' if complete else ' (list incomplete)'}, {len(new)} new, {len(stale)} re-checked, "
        f"{len(gone)} gone; {db.execute('SELECT COUNT(*) FROM company_loc').fetchone()[0]} located")


def _store_owners(c, db, owners):
    for u, d in c.lookup_users(owners).items():
        db.execute("INSERT INTO users(id,country,mu,name) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET country=excluded.country, mu=excluded.mu, name=excluded.name",
                   (u, d.get("country"), d.get("mu"), d.get("username")))
        db.execute("INSERT OR REPLACE INTO names VALUES('user',?,?,NULL)", (u, d.get("username")))


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
                         d.get("region"), owner_country.get(owner), ts, len(ws), round(wages, 6), round(mgr, 6)))
    # drop companies that left the alliance's countries, closed or disappeared from the index
    keep = {r["id"] for r in db.execute("SELECT id, region FROM company_loc WHERE disabled=0") if r["region"] in host_regions}
    db.executemany("DELETE FROM companies WHERE id=?", [(r["id"],) for r in db.execute("SELECT id FROM companies").fetchall() if r["id"] not in keep])
    db.executemany("INSERT OR REPLACE INTO companies(id,name,owner,item,value,region,owner_country,seen,workers,wages,mgr) VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
    allrows = [tuple(r) for r in db.execute("SELECT id,name,owner,item,value,region,owner_country,seen,workers,wages,mgr FROM companies")]
    snapshot_wages(db, allrows)
    db.commit()
    log(f"companies: {len(rows)} refreshed this run, {len(allrows)} stored")
