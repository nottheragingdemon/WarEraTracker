import os
import json, datetime as dt, re

ISO = "%Y-%m-%dT%H:%M:%S.%fZ"


def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime(ISO)[:-4] + "Z"


def parse_when(s, default=None):
    """'7d', '36h', '2026-11-20' or full ISO -> ISO string (UTC)."""
    if not s:
        return default
    m = re.fullmatch(r"(\d+)([dhm])", s.strip())
    if m:
        n, u = int(m.group(1)), m.group(2)
        delta = {"d": dt.timedelta(days=n), "h": dt.timedelta(hours=n), "m": dt.timedelta(minutes=n)}[u]
        return (dt.datetime.now(dt.timezone.utc) - delta).strftime(ISO)[:-4] + "Z"
    if len(s) == 10:
        s += "T00:00:00.000Z"
    return s


def log(*a):
    print(*a, flush=True)


class Scope:
    """What to collect: battles involving a member country of one alliance, created since a date."""
    def __init__(self, db, alliance=None, since=None):
        self.alliance_id, self.members, self.since = None, set(), since
        if alliance:
            r = db.execute("SELECT eid FROM names WHERE etype='alliance' AND (eid=? OR lower(name)=lower(?))", (alliance, alliance)).fetchone()
            if not r:
                raise SystemExit(f"alliance '{alliance}' not found; run `collect --what alliances` first (needs an API key)")
            self.alliance_id = r["eid"]
            self.members = {m["country"] for m in db.execute("SELECT country FROM alliance_members WHERE alliance=?", (self.alliance_id,))}

    @property
    def active(self):
        return bool(self.alliance_id)

    def battle_sql(self, alias="b"):
        """SQL condition (with args) restricting a battles table to the scope."""
        conds, args = [], []
        if self.since:
            conds.append(f"{alias}.created_at>=?"); args.append(self.since)
        if self.members:
            ph = ",".join("?" * len(self.members))
            conds.append(f"({alias}.att_country IN ({ph}) OR {alias}.def_country IN ({ph}))")
            args += list(self.members) * 2
        return (" AND ".join(conds) or "1=1"), args


def collect_battles(c, db, since, scope=None):
    ts, n = now_iso(), 0
    extra = {"allianceId": scope.alliance_id} if scope and scope.alliance_id else {}
    batches = [c.pages("battle.getBattles", isActive=True, limit=100, **extra)]

    def ended():
        for b in c.pages("battle.getBattles", isActive=False, limit=100, **extra):
            if b["createdAt"] < since:
                return
            yield b
    batches.append(ended())
    for gen in batches:
        for b in gen:
            n += 1
            a, d = b["attacker"], b["defender"]
            db.execute("""INSERT INTO battles(id,war,type,created_at,ended_at,is_active,att_country,def_country,def_region,won_by,
                att_damage,def_damage,att_hits,def_hits,rounds_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET ended_at=excluded.ended_at,is_active=excluded.is_active,won_by=excluded.won_by,
                att_damage=excluded.att_damage,def_damage=excluded.def_damage,att_hits=excluded.att_hits,
                def_hits=excluded.def_hits,rounds_json=excluded.rounds_json""",
                (b["_id"], b.get("war"), b.get("type"), b["createdAt"], b.get("endedAt"), int(b["isActive"]),
                 a.get("country"), d.get("country"), d.get("region"), b.get("wonBy"),
                 a.get("damages"), d.get("damages"), a.get("hitCount"), d.get("hitCount"),
                 json.dumps(b.get("roundsHistory", []))))
            for side, s in (("attacker", a), ("defender", d)):
                for kind, key in (("country", "countryOrders"), ("mu", "muOrders")):
                    for eid in s.get(key) or []:
                        eid = eid if isinstance(eid, str) else eid.get("_id") or json.dumps(eid)
                        db.execute("""INSERT INTO orders VALUES(?,?,?,?,?,?)
                            ON CONFLICT(battle_id,side,kind,eid) DO UPDATE SET last_seen=excluded.last_seen""",
                                   (b["_id"], side, kind, eid, ts, ts))
        db.commit()
    log(f"battles: {n} stored")


LEVELS = ("country", "mu", "user")


def collect_stats(c, db, levels=LEVELS, limit=None, pages=None, scope=None):
    """Per-battle damage and money rankings per side, country level first (country is the priority)."""
    pages = pages or {"country": 2, "mu": 3, "user": 2}
    for level in levels:
        cond, cargs = scope.battle_sql("b") if scope else ("1=1", [])
        todo = db.execute(f"""SELECT b.id FROM battles b LEFT JOIN battle_fetch f ON f.battle_id=b.id AND f.level=?
            WHERE (f.fetched_at IS NULL OR b.is_active=1 OR (b.ended_at IS NOT NULL AND f.fetched_at < b.ended_at)) AND {cond}
            ORDER BY b.created_at DESC""", (level, *cargs)).fetchall()
        if limit:
            todo = todo[:limit]
        log(f"{level}: {len(todo)} battles to fetch")
        for i, r in enumerate(todo, 1):
            bid, rows = r["id"], []
            for kind in ("damage", "money"):
                for side in ("attacker", "defender"):
                    for e in c.pages("battleRanking.getRanking", max_pages=pages[level], battleId=bid, dataType=kind,
                                     type=level, side=side, limit=100):
                        if e.get(level) and e.get("value"):
                            rows.append((bid, kind, level, e[level], side[0], e["value"]))
            if level == "country":   # alliances ride along with the country level (merged damage)
                for e in c.pages("battleRanking.getRanking", max_pages=2, battleId=bid, dataType="damage",
                                 type="alliance", side="merged", limit=100):
                    if e.get("alliance") and e.get("value"):
                        rows.append((bid, "damage", "alliance", e["alliance"], "m", e["value"]))
            db.execute("DELETE FROM battle_stat WHERE battle_id=? AND etype IN (?,?)", (bid, level, "alliance" if level == "country" else level))
            db.executemany("INSERT OR REPLACE INTO battle_stat VALUES(?,?,?,?,?,?)", rows)
            db.execute("INSERT OR REPLACE INTO battle_fetch VALUES(?,?,?)", (bid, level, now_iso()))
            db.commit()
            if i % 20 == 0 or i == len(todo):
                log(f"  {level} {i}/{len(todo)} (api calls so far: {c.n})")


def collect_people(c, db, user_limit=800, scope=None):
    """MU list (names, country, members) and per-player country/name so filters can cascade."""
    n = 0
    db.execute("DELETE FROM mu_members")
    for m in c.pages("mu.getManyPaginated", limit=100):
        n += 1
        db.execute("INSERT OR REPLACE INTO mus VALUES(?,?,?)", (m["_id"], m["name"], m.get("country")))
        db.execute("INSERT OR REPLACE INTO names VALUES('mu',?,?,NULL)", (m["_id"], m["name"]))
        for u in m.get("members", []):
            db.execute("INSERT OR IGNORE INTO mu_members VALUES(?,?)", (m["_id"], u))
    db.commit()
    log(f"people: {n} MUs, {db.execute('SELECT COUNT(*) FROM mu_members').fetchone()[0]} members")
    cond, cargs = scope.battle_sql("b") if scope else ("1=1", [])
    todo = db.execute(f"""SELECT s.eid, SUM(s.value) v FROM battle_stat s JOIN battles b ON b.id=s.battle_id
        LEFT JOIN users u ON u.id=s.eid
        WHERE s.etype='user' AND s.kind='damage' AND (u.id IS NULL OR u.name IS NULL OR u.country IS NULL) AND {cond}
        GROUP BY s.eid ORDER BY v DESC LIMIT ?""", (*cargs, user_limit)).fetchall()
    for i, r in enumerate(todo, 1):
        try:
            u = c.call("user.getUserLite", userId=r["eid"])
        except Exception:
            continue
        db.execute("INSERT OR REPLACE INTO users VALUES(?,?,?,?)", (r["eid"], u.get("country"), u.get("mu"), u.get("username")))
        db.execute("INSERT OR REPLACE INTO names VALUES('user',?,?,NULL)", (r["eid"], u.get("username")))
        if i % 200 == 0:
            db.commit(); log(f"  players {i}/{len(todo)}")
    db.commit()
    log(f"people: {len(todo)} players resolved")


BOUNTY_TYPES = {"userBounty": "user", "muBounty": "mu", "countryBounty": "country"}


def collect_bounty(c, db, top=200, scope=None):
    """Bounty ranking snapshots. With a scope only the alliance's countries, their MUs and their players are kept."""
    ts = now_iso()
    members = scope.members if scope and scope.members else None
    mu_country = {r["id"]: r["country"] for r in db.execute("SELECT id,country FROM mus")}

    def keep(rtype, e, key):
        if not members:
            return True
        if key == "country":
            return e.get("country") in members
        if key == "mu":
            return (e.get("country") or mu_country.get(e.get(key))) in members or mu_country.get(e.get(key)) in members
        return e.get("country") in members

    for rtype, key in BOUNTY_TYPES.items():
        n = 0
        if key == "user" and members:   # players: ask per member country so the top N is per country
            streams = [c.pages("ranking.getRankingPage", rankingType=rtype, limit=50, max_pages=max(1, top // 50), countryId=m) for m in members]
        else:
            streams = [c.pages("ranking.getRankingPage", rankingType=rtype, limit=50, max_pages=max(1, top // 50))]
        for st in c.map(list, streams):   # one thread per country stream
            for e in st:
                eid = e.get(key)
                if not eid or not keep(rtype, e, key):
                    continue
                db.execute("INSERT OR REPLACE INTO bounty_snap VALUES(?,?,?,?,?,?)",
                           (ts, rtype, eid, e["value"], e.get("country"), e.get("mu")))
                if key == "user":
                    db.execute("INSERT INTO users(id,country,mu) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET country=COALESCE(excluded.country,country), mu=COALESCE(excluded.mu,mu)",
                               (eid, e.get("country"), e.get("mu")))
                n += 1
        log(f"bounty: {rtype} {n} entries")
    db.commit()


def collect_wealth(c, db, top=200, scope=None):
    """Richest players (userWealth ranking) per member country, newest snapshot only; unnamed players are looked up."""
    members = scope.members if scope and scope.members else None
    ts = now_iso()
    if members:
        streams = [c.pages("ranking.getRankingPage", rankingType="userWealth", limit=50, max_pages=max(1, top // 50), countryId=m) for m in members]
    else:
        streams = [c.pages("ranking.getRankingPage", rankingType="userWealth", limit=50, max_pages=max(1, top // 50))]
    rows = []
    for st in c.map(list, streams):
        for e in st:
            if e.get("user") and (not members or e.get("country") in members):
                rows.append((e["user"], e.get("country"), e.get("mu"), e["value"], e.get("rank"), ts))
    if not rows:
        log("wealth: no data, kept the previous snapshot"); return
    db.execute("DELETE FROM wealth_now")
    db.executemany("INSERT OR REPLACE INTO wealth_now VALUES(?,?,?,?,?,?)", rows)
    for r in rows:
        db.execute("INSERT INTO users(id,country,mu) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET country=COALESCE(excluded.country,country), mu=COALESCE(excluded.mu,mu)", (r[0], r[1], r[2]))
    need = [r["id"] for r in db.execute("SELECT u.id FROM users u JOIN wealth_now w ON w.eid=u.id WHERE u.name IS NULL")]
    for u, d in c.lookup_users(need).items():
        db.execute("UPDATE users SET name=? WHERE id=?", (d.get("username"), u))
        db.execute("INSERT OR REPLACE INTO names VALUES('user',?,?,NULL)", (u, d.get("username")))
    db.commit()
    log(f"wealth: {len(rows)} players ranked, {len(need)} names looked up")


def collect_transfers(c, db, scope=None, days=90):
    """Country money transfers between the alliance's member countries (transactionType countryMoneyTransfer).
    Newest first per country; stops at the first transaction already stored or older than `days`."""
    members = set(scope.members) if scope and scope.members else set()
    if not members:
        log("transfers: no alliance members in scope, skipped"); return
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    known = {r["id"] for r in db.execute("SELECT id FROM transfers")}
    new = 0
    def fresh(m):   # newest first until something already stored or too old
        out = []
        for t in c.pages("transaction.getPaginatedTransactions", max_pages=60, countryId=m, transactionType="countryMoneyTransfer", limit=100):
            if t["_id"] in known or t["createdAt"] < cutoff:
                break
            out.append(t)
        return out
    for found in c.map(fresh, sorted(members)):   # the countries are read in parallel, written one after another
        for t in found:
            if t.get("sellerCountryId") in members and t.get("buyerCountryId") in members:
                db.execute("INSERT OR IGNORE INTO transfers VALUES(?,?,?,?,?)", (t["_id"], t["createdAt"], t["sellerCountryId"], t["buyerCountryId"], t.get("money") or 0))
                new += 1
    db.commit()
    log(f"transfers: {new} new between member countries")


def collect_donations(c, db, scope=None, days=60, budget=300.0):
    """Player donations to each member country's treasury (transactionType donation), newest first; stops at the first
    one already stored or older than `days`. The donor's own country is looked up so citizens' donations can be separated."""
    import time as _t
    members = set(scope.members) if scope and scope.members else set()
    if not members:
        log("donations: no alliance members in scope, skipped"); return
    t0 = _t.monotonic()
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    known = {r["id"] for r in db.execute("SELECT id FROM donations")}
    new = 0
    def fresh(m):
        out = []
        for t in c.pages("transaction.getPaginatedTransactions", max_pages=80, countryId=m, transactionType="donation", limit=100):
            if t["_id"] in known or t["createdAt"] < cutoff or _t.monotonic() - t0 > budget:
                break
            out.append(t)
        return out
    for m, found in zip(sorted(members), c.map(fresh, sorted(members))):
        for t in found:
            if t.get("sellerCountryId") == m and t.get("buyerId"):
                row = db.execute("SELECT country FROM users WHERE id=?", (t["buyerId"],)).fetchone()
                db.execute("INSERT OR IGNORE INTO donations VALUES(?,?,?,?,?,?)", (t["_id"], t["createdAt"], m, t["buyerId"], t.get("money") or 0, row["country"] if row else None))
                new += 1
    db.commit()
    need = [r["donor"] for r in db.execute("SELECT DISTINCT donor FROM donations WHERE donor_country IS NULL")]
    looked = 0
    for u, d in c.lookup_users(need).items():
        if d.get("country"):
            db.execute("UPDATE donations SET donor_country=? WHERE donor=?", (d["country"], u)); looked += 1
    db.execute("DELETE FROM donations WHERE ts < ?", (cutoff,))
    db.commit()
    nameless = [r["donor"] for r in db.execute("SELECT DISTINCT d.donor FROM donations d LEFT JOIN users u ON u.id=d.donor WHERE d.donor_country=d.country AND (u.name IS NULL)")]
    for u, d in c.lookup_users(nameless).items():
        if d.get("username"):
            db.execute("INSERT INTO users(id,name,country) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name", (u, d["username"], d.get("country")))
            db.execute("INSERT OR REPLACE INTO names VALUES('user',?,?,NULL)", (u, d["username"]))
    db.commit()
    log(f"donations: {new} new, {looked} donors looked up, {len(need) - looked} still unknown")


STATUSES = ["active", "won", "expiredNoBids", "expiredBattle", "expiredRound", "cancelled"]


def collect_contracts(c, db, since, scope=None):
    """Mercenary contracts since a date; with a scope, only those tied to an in-scope battle are kept."""
    keep_b = None
    if scope and scope.active:
        cond, cargs = scope.battle_sql("b")
        keep_b = {r[0] for r in db.execute(f"SELECT id FROM battles b WHERE {cond}", cargs)}
    n = seen = 0
    for st in STATUSES:
        for a in c.pages("mercenaryContractAuction.getPaginatedAuctions", status=st, limit=50):
            if a["createdAt"] < since:
                break
            seen += 1
            if keep_b is not None and a.get("battle") not in keep_b:
                continue
            n += 1
            db.execute("INSERT OR REPLACE INTO contracts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (a["_id"], a.get("battle"), a.get("country"), a.get("createdBy"), a.get("forCountry"),
                        a.get("forCountrySide"), a.get("minimumDamage"), a.get("budget"), a.get("initialPerK"),
                        a.get("currentPerK"), a.get("currentPayout"), a.get("duration"), a.get("status"),
                        a["createdAt"], a.get("expiresAt"), a.get("currentWinner"), a.get("currentWinnerUser"),
                        json.dumps(a.get("bids", [])), a.get("updatedAt")))
        db.commit()
    log(f"contracts: {n} stored ({seen} seen)")


def collect_alliances(c, db):
    """Alliance names and member countries (needs an API key; skipped without one)."""
    if not c.key:
        log("alliances: skipped (no API key)"); return
    items = c.call("alliance.getManyPaginated", page=1, limit=100)["items"]
    db.execute("DELETE FROM alliance_members")
    for a in items:
        db.execute("INSERT OR REPLACE INTO alliances VALUES(?,?,?)", (a["_id"], a["name"], a.get("leader")))
        db.execute("INSERT OR REPLACE INTO names VALUES('alliance',?,?,NULL)", (a["_id"], a["name"]))
        for m in a.get("memberCountries", []):
            db.execute("INSERT OR IGNORE INTO alliance_members VALUES(?,?)", (a["_id"], m["country"]))
    db.commit()
    log(f"alliances: {len(items)} stored")


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
        for ct in c.call("country.getAllCountries"):
            tx = ct.get("taxes") or {}
            cur = (tx.get("income"), tx.get("manager"))
            if lastr.get(ct["_id"]) != cur:
                db.execute("INSERT OR REPLACE INTO rate_hist VALUES(?,?,?,?)", (ct["_id"], now, cur[0], cur[1]))
            db.execute("INSERT OR REPLACE INTO country_tax VALUES(?,?,?,?,?)",
                       (ct["_id"], ct.get("name"), tx.get("income"), tx.get("manager"), tx.get("market")))
            cw = (ct.get("rankings") or {}).get("countryWealth") or {}
            db.execute("INSERT OR REPLACE INTO country_now VALUES(?,?,?,?,?,?,?,?)",
                       (ct["_id"], ct.get("name"), ct.get("money"), cw.get("value"), cw.get("rank"),
                        ct.get("currentPopulation"), ct.get("currentDevelopment"), now_iso()))
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
        for (cid, d), e in zip(active, est):
            ws = d.get("workers") or []
            if e:
                wages, mgr = float(e.get("wageCost") or 0), float(e.get("managerCost") or 0)
            else:  # estimate unavailable: fall back to the wages listed on the company
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
