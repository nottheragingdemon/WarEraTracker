"""Export the database to a compact data.json for the dashboard page (no network access needed)."""
import json, os, datetime as dt

SIDE = {"a": 0, "d": 1, "m": 2}
KIND = {"damage": 0, "money": 1}


CAP_MS = 6 * 3600 * 1000  # a check counts for at most 6h, so a missed run doesn't invent hours


def tax_history(db):
    """Hourly region tax (employee+manager) integrated over time: {day: {h: hours tracked, r: {region: owed}}}.
    Each check's rate is held until the next check (at most CAP_MS), split across UTC days."""
    runs = [r["t"] for r in db.execute("SELECT t FROM run_log ORDER BY t")]
    if not runs:
        return {"firstT": None, "lastT": None, "everyMinutes": None, "days": {}}
    hist = {}
    for r in db.execute("SELECT region,t,emp+mgr AS v FROM region_rate ORDER BY region,t"):
        hist.setdefault(r["region"], []).append((r["t"], r["v"]))
    days = {}
    DAY = 86400000
    gaps = []
    import bisect
    for i in range(len(runs) - 1):
        t0 = runs[i]; t1 = min(runs[i + 1], t0 + CAP_MS); gaps.append(runs[i + 1] - t0)
        a = t0
        while a < t1:
            ds = a - a % DAY; b = min(t1, ds + DAY); hrs = (b - a) / 3600000
            key = dt.datetime.fromtimestamp(ds / 1000, dt.timezone.utc).strftime("%Y-%m-%d")
            d = days.setdefault(key, {"h": 0.0, "r": {}}); d["h"] += hrs
            for rid, h in hist.items():
                k = bisect.bisect_right(h, (t0, float("inf"))) - 1
                if k >= 0 and h[k][1]:
                    d["r"][rid] = d["r"].get(rid, 0.0) + h[k][1] * hrs
            a = b
    for d in days.values():
        d["h"] = round(d["h"], 3); d["r"] = {k: round(v, 2) for k, v in d["r"].items()}
    gaps.sort()
    return {"firstT": runs[0], "lastT": runs[-1], "everyMinutes": round(gaps[len(gaps) // 2] / 60000) if gaps else None, "days": days}


SKILLS = ["companies", "energy", "management", "production", "attack", "precision", "criticalChance", "criticalDamages", "armor", "dodge",
          "health", "hunger", "stamina", "lootChance"]   # the first four are the economy skills


def company_history(db, E, days=35, full_hours=48, bucket_hours=6):
    """Wage history per (host country, owner country) for the Company tax tracker: every snapshot from the last 48 hours,
    the last one in each 6-hour block before that, for 35 days. Rows: [host, owner country, t, companies, workers, wages/h, manager pay/h].
    Older per-region snapshots (wage_snap, before 27 Nov 2026) are summed to the same level."""
    import time
    now = int(time.time() * 1000)
    lo, full_from, bucket = now - days * 864e5, now - full_hours * 36e5, int(bucket_hours * 36e5)
    series = {}
    host_of = {r["region"]: r["country"] for r in db.execute("SELECT region, country FROM region_now")}
    # old per-region snapshots: step series per region, summed per (host, owner) at every change
    old = {}
    for r in db.execute("SELECT * FROM wage_snap WHERE t>=? ORDER BY t", (lo,)):
        h = host_of.get(r["region"])
        if h and r["owner_country"]:
            old.setdefault((h, r["owner_country"]), []).append((r["t"], r["region"], (r["companies"], r["workers"], r["wages"], r["mgr"] or 0)))
    for k, evs in old.items():
        cur, out = {}, []
        for t, reg, v in evs:
            cur[reg] = v
            tot = [sum(x[i] for x in cur.values()) for i in range(4)]
            if out and out[-1][0] == t:
                out[-1] = (t, tot)
            else:
                out.append((t, tot))
        series.setdefault(k, []).extend(out)
    for r in db.execute("SELECT * FROM wage_snap2 WHERE t>=? ORDER BY t", (lo,)):
        series.setdefault((r["host"], r["owner_country"]), []).append((r["t"], [r["companies"], r["workers"], r["wages"], r["mgr"] or 0]))
    rows = []
    for (h, o), evs in series.items():
        evs.sort(key=lambda x: x[0])
        keep, last_bucket = [], {}
        for t, v in evs:
            if t >= full_from:
                keep.append((t, v))
            else:
                last_bucket[t // bucket] = (t, v)   # the last snapshot in each block wins
        for t, v in sorted(last_bucket.values()) + keep:
            rows.append([E("country", h), E("country", o), t, v[0], v[1], round(v[2], 4), round(v[3], 4)])
    rows.sort(key=lambda r: r[2])
    return rows


def company_index_status(db):
    meta = lambda k: (db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone() or [None])[0]
    q = lambda sql, *a: db.execute(sql, a).fetchone()[0]
    pass_no = int(meta("index_pass") or 0)
    return {"known": q("SELECT COUNT(*) FROM company_loc"), "located": q("SELECT COUNT(*) FROM company_loc WHERE checked IS NOT NULL"),
            "pass": pass_no, "passListed": q("SELECT COUNT(*) FROM company_loc WHERE listed=?", pass_no) if pass_no else 0,
            "passDone": not meta("index_cursor"), "fullAt": meta("index_full_at")}


def company_coverage(db, E, scope=None):
    """Per alliance host country: the tracker's companies, workers and wage tax per hour (all owners) against the game's own region figures."""
    from .stages.common import alliance_countries
    hosts = alliance_countries(db) or set(scope.members if scope and scope.members else [])
    rate = {r["country"]: (r["income"] or 0, r["manager"] or 0) for r in db.execute("SELECT country, income, manager FROM country_tax")}
    out = []
    for h in sorted(hosts):
        g = db.execute("SELECT COALESCE(SUM(companies),0) co, COALESCE(SUM(employees),0) em, COALESCE(SUM(emp),0)+COALESCE(SUM(mgr),0) tax FROM region_now WHERE country=?", (h,)).fetchone()
        t = db.execute("""SELECT COUNT(*) n, COALESCE(SUM(c.workers>0),0) staffed, COALESCE(SUM(c.workers),0) w, COALESCE(SUM(c.wages),0) wg, COALESCE(SUM(c.mgr),0) mg
            FROM companies c JOIN region_now r ON r.region=c.region WHERE r.country=?""", (h,)).fetchone()
        ri, rm = rate.get(h, (0, 0))
        out.append([E("country", h), t["n"], t["staffed"], t["w"], round(t["wg"] * ri / 100 + t["mg"] * rm / 100, 3), g["co"], g["em"], round(g["tax"], 3)])
    return out


def export(db, out, since, scope=None):
    ents, eidx = [], {}

    def E(t, i):
        if not i:
            return -1
        k = (t, i)
        if k not in eidx:
            eidx[k] = len(ents); ents.append([t, i, None])
        return eidx[k]

    cond, cargs = scope.battle_sql("b") if scope else ("b.created_at>=?", [since])
    bs = db.execute(f"SELECT * FROM battles b WHERE {cond} ORDER BY b.created_at", cargs).fetchall()
    bidx = {b["id"]: n for n, b in enumerate(bs)}
    battles = [[b["id"], b["type"], b["created_at"], b["ended_at"], E("country", b["att_country"]), E("country", b["def_country"]),
                b["att_damage"] or 0, b["def_damage"] or 0, b["won_by"], b["is_active"], E("region", b["def_region"])] for b in bs]
    stats = []
    for r in db.execute("SELECT * FROM battle_stat"):
        bi = bidx.get(r["battle_id"])
        if bi is None:
            continue
        stats.append([KIND[r["kind"]], bi, E(r["etype"], r["eid"]), SIDE[r["side"]], round(r["value"], 2)])
    orders = [[bidx[r["battle_id"]], r["side"][0], E(r["kind"], r["eid"]), r["first_seen"], r["last_seen"]]
              for r in db.execute("SELECT * FROM orders") if r["battle_id"] in bidx]
    kind = {"userBounty": "user", "muBounty": "mu", "countryBounty": "country"}
    mc = {r["id"]: r["country"] for r in db.execute("SELECT id,country FROM mus")}
    members = scope.members if scope and scope.members else None

    def in_scope(r):
        if not members:
            return True
        t = r["rtype"]
        c = r["eid"] if t == "countryBounty" else (mc.get(r["eid"]) if t == "muBounty" else r["country"])
        return c in members
    bounty = [[r["ts"], E(kind[r["rtype"]], r["eid"]), r["value"], E("country", r["country"]), E("mu", r["mu"])]
              for r in db.execute("SELECT * FROM bounty_snap WHERE ts>=?", (since,)) if in_scope(r)]
    contracts = []
    for r in db.execute("SELECT * FROM contracts WHERE created_at>=?", (since,)):
        if scope and scope.active and r["battle_id"] not in bidx:
            continue
        bids = json.loads(r["bids_json"] or "[]")
        contracts.append([r["id"], bidx.get(r["battle_id"], -1), r["created_at"], r["status"], E("country", r["for_country"]),
                          r["side"], r["min_damage"], r["budget"], r["current_payout"], E("mu", r["winner_mu"]), E("user", r["winner_user"]),
                          E("user", r["created_by"]), sorted({E("mu", b.get("mu")) for b in bids if b.get("mu")}),
                          sorted({E("user", b.get("user")) for b in bids if b.get("user")}), len(bids)])
    # relations so the page can cascade filters: MU -> country, player -> (country, MU)
    mu_country = {r["id"]: r["country"] for r in db.execute("SELECT id,country FROM mus")}
    user_mu = {r["user"]: r["mu"] for r in db.execute("SELECT user,mu FROM mu_members")}
    user_row = {r["id"]: r for r in db.execute("SELECT * FROM users")}
    rel_mu, rel_user = {}, {}
    for _ in range(2):  # second pass picks up entities added while resolving relations
        for i, (t, eid, _n) in enumerate(list(ents)):
            if t == "mu" and eid in mu_country and str(i) not in rel_mu:
                rel_mu[str(i)] = E("country", mu_country[eid])
            if t == "user" and str(i) not in rel_user:
                u = user_row.get(eid)
                mu = (u["mu"] if u and u["mu"] else None) or user_mu.get(eid)
                country = (u["country"] if u and u["country"] else None) or mu_country.get(mu)
                rel_user[str(i)] = [E("country", country), E("mu", mu)]
    companies, companies_at = [], None
    for r in db.execute("SELECT * FROM companies ORDER BY value DESC"):
        companies.append([r["name"], E("user", r["owner"]), r["item"], round(r["value"] or 0), r["region"], E("country", r["owner_country"]),
                          r["workers"] or 0, round(r["wages"] or 0, 6), round(r["mgr"] or 0, 6)])
        companies_at = r["seen"]
    country_now = {str(E("country", r["country"])): [r["money"], r["wealth"], r["wealth_rank"], r["population"], r["development"],
                                                     json.loads(r["income"]) if r["income"] else None]
                   for r in db.execute("SELECT * FROM country_now")}
    # player efficiency: latest values, the snapshot from about a week ago (the oldest of the last 7 days), skill allocation
    today = dt.datetime.now(dt.timezone.utc).date()
    lo = (today - dt.timedelta(days=7)).isoformat()
    then = {}
    for r in db.execute("SELECT eid, day, wealth, dmg_total FROM player_snap WHERE day>=? AND day<? ORDER BY day DESC", (lo, today.isoformat())):
        then[r["eid"]] = (r["day"], r["wealth"], r["dmg_total"])   # descending, so the oldest day wins
    skills = {r["eid"]: r for r in db.execute("SELECT * FROM player_skill")}
    prev = {}
    for r in db.execute("SELECT eid, checked, spent, eco FROM player_skill_hist ORDER BY checked"):
        prev[r["eid"]] = (r["spent"], r["eco"])   # latest earlier allocation wins
    players = []
    for r in db.execute("SELECT * FROM player_now"):
        sk, th = skills.get(r["eid"]), then.get(r["eid"])
        players.append([E("user", r["eid"]), E("country", r["country"]), E("mu", r["mu"]), round(r["wealth"] or 0, 2), round(r["dmg_total"] or 0),
                        round(r["dmg_week"] or 0), th[0] if th else None, round(th[1] or 0, 2) if th else None, round(th[2] or 0) if th else None,
                        sk["spent"] if sk else None, sk["eco"] if sk else None,
                        [json.loads(sk["levels"]).get(k, 0) for k in SKILLS] if sk else None,
                        (sk["reset_at"] or None) if sk else None, list(prev[r["eid"]]) if r["eid"] in prev else None])
    # daily history for the trend charts: the last 30 days of wealth and total damage per tracked player
    days = sorted({r["day"] for r in db.execute("SELECT DISTINCT day FROM player_snap WHERE day>=?", ((today - dt.timedelta(days=30)).isoformat(),))})
    di = {d: i for i, d in enumerate(days)}
    hist = {}
    for r in db.execute("SELECT eid, day, wealth, dmg_total FROM player_snap WHERE day>=?", (days[0] if days else "9",)):
        h = hist.setdefault(r["eid"], [[None] * len(days), [None] * len(days)])
        h[0][di[r["day"]]], h[1][di[r["day"]]] = round(r["wealth"] or 0), round(r["dmg_total"] or 0)
    player_hist = {"days": days, "rows": [[E("user", u), h[0], h[1]] for u, h in hist.items()
                                          if u in {p for (p,) in db.execute("SELECT eid FROM player_now")}]}
    wealth = [[E("user", r["eid"]), E("country", r["country"]), E("mu", r["mu"]), r["value"], r["rank"]]
              for r in db.execute("SELECT * FROM wealth_now ORDER BY value DESC")]
    transfers = [[r["ts"], E("country", r["sender"]), E("country", r["receiver"]), r["money"]]
                 for r in db.execute("SELECT * FROM transfers ORDER BY ts DESC")]
    donations = [[r["day"], E("country", r["country"]), r["own"], r["own_n"], r["total"]]
                 for r in db.execute("SELECT substr(ts,1,10) day, country, SUM(CASE WHEN donor_country=country THEN money ELSE 0 END) own, "
                                     "SUM(CASE WHEN donor_country=country THEN 1 ELSE 0 END) own_n, SUM(money) total FROM donations GROUP BY day, country ORDER BY day DESC")]
    donors = [[r["day"], E("country", r["country"]), E("user", r["donor"]), r["total"], r["n"]]
              for r in db.execute("SELECT substr(ts,1,10) day, country, donor, SUM(money) total, COUNT(*) n FROM donations "
                                  "WHERE donor_country=country GROUP BY day, country, donor ORDER BY day DESC")]
    regions_now = {r["region"]: [r["name"], E("country", r["country"]), r["emp"], r["mgr"], r["companies"], r["employees"]]
                   for r in db.execute("SELECT * FROM region_now")}
    country_tax = {str(E("country", r["country"])): [r["income"], r["manager"]] for r in db.execute("SELECT * FROM country_tax")}
    wage_hist = company_history(db, E)
    rate_hist = {}
    for r in db.execute("SELECT * FROM rate_hist ORDER BY t"):
        rate_hist.setdefault(str(E("country", r["country"])), []).append([r["t"], r["income"], r["manager"]])
    runs = [r["t"] for r in db.execute("SELECT t FROM run_log ORDER BY t DESC LIMIT 1500")][::-1]
    for e in ents:
        r = db.execute("SELECT name FROM names WHERE etype=? AND eid=?", (e[0], e[1])).fetchone()
        e[2] = r["name"] if r else None
    alliances = {}
    for r in db.execute("SELECT alliance,country FROM alliance_members"):
        alliances.setdefault(E("alliance", r["alliance"]), []).append(E("country", r["country"]))
    for e in ents:
        if e[2] is None:
            r = db.execute("SELECT name FROM names WHERE etype=? AND eid=?", (e[0], e[1])).fetchone()
            e[2] = r["name"] if r else None
    # packed per-battle stats (about half the size): [[kind, battle, [entity*3+side, value, ...]], ...]; theme.js weStats() unpacks
    packed = {}
    for k, b, e, sd, v in stats:
        packed.setdefault((k, b), []).extend([e * 3 + sd, int(v) if v == int(v) else v])
    stats_p = [[k, b, f] for (k, b), f in packed.items()]
    # country income by day for the alliance's countries: the average hourly rate of each stream that day x 24, hours sampled, last treasury
    days_back = (today - dt.timedelta(days=60)).isoformat()
    inc_days = {}
    for r in db.execute("SELECT country, t, money, income FROM country_income ORDER BY t"):
        day = dt.datetime.fromtimestamp(r["t"] / 1000, dt.timezone.utc).date().isoformat()
        if day < days_back:
            continue
        x = inc_days.setdefault((r["country"], day), {"n": 0, "sum": {}, "money": None})
        x["n"] += 1
        x["money"] = r["money"]
        for k, v in json.loads(r["income"]).items():
            x["sum"][k] = x["sum"].get(k, 0) + float(v or 0)
    country_income_days = [[E("country", c), day, x["n"], round(x["money"] or 0, 2), {k: round(v / x["n"] * 24, 2) for k, v in x["sum"].items()}]
                           for (c, day), x in sorted(inc_days.items(), key=lambda kv: kv[0][1])]
    # market trades per member country per day (value, count) for the market tax estimate, with each country's market tax rate
    trade_days = [[E("country", r["country"]), r["day"], round(r["v"], 2), r["n"]] for r in db.execute(
        "SELECT country, substr(ts,1,10) day, SUM(money) v, COUNT(*) n FROM trades GROUP BY country, day ORDER BY day")]
    market_rate = {str(E("country", r["country"])): r["market"] for r in db.execute("SELECT country, market FROM country_tax")}
    # Status page: recent collector runs, alert and digest marks, backups, table sizes
    def state(k):
        try:
            r = db.execute("SELECT v FROM alert_state WHERE k=?", (k,)).fetchone()
            return r[0] if r else None
        except Exception:
            return None
    status = {"runs": [[r["ts"], r["kind"], r["seconds"], r["calls"], r["gw"], r["skipped"], json.loads(r["timings"] or "[]")]
                       for r in db.execute("SELECT * FROM run_stats ORDER BY ts DESC LIMIT 200")],
              "digestAt": state("digest_at"), "lastBattleAlert": state("battle_created"), "lastEndAlert": state("battle_ended"),
              "lastBackup": os.environ.get("LAST_BACKUP") or None, "gateway": os.environ.get("WARERA_GATEWAY", "1") != "0",
              "rows": {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
                       ("battles", "battle_stat", "bounty_snap", "contracts", "companies", "transfers", "donations", "player_snap", "player_skill", "country_income", "trades")},
              "companyIndex": company_index_status(db), "coverage": company_coverage(db, E, scope),
              "donationsSince": db.execute("SELECT MIN(ts) FROM donations").fetchone()[0],
              "transfersSince": db.execute("SELECT MIN(ts) FROM transfers").fetchone()[0]}
    data = {"v": 3, "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "since": since,
            "ents": ents, "battles": battles, "statsP": stats_p, "orders": orders, "bounty": bounty, "contracts": contracts,
            "alliances": alliances, "relMu": rel_mu, "relUser": rel_user, "taxHist": tax_history(db), "companies": companies, "companiesAt": companies_at,
            "regionsNow": regions_now, "countryNow": country_now, "transfers": transfers, "donations": donations, "donors": donors, "wealthNow": wealth, "countryTax": country_tax,
            "wageHist": wage_hist, "rateHist": rate_hist, "runs": runs, "players": players, "skillOrder": SKILLS, "playerHist": player_hist, "status": status, "countryIncomeDays": country_income_days, "tradeDays": trade_days, "marketRate": market_rate}
    # bounty history and contracts are only used by Ask WarEra: they go to a second file so the other pages download less
    extra = {k: data.pop(k) for k in ("bounty", "contracts")}
    company_extra = {k: data.pop(k) for k in ("wageHist", "companies")}   # only the Company page and Ask WarEra need these
    with open(out, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    with open(os.path.join(os.path.dirname(out) or ".", "ask-data.json"), "w") as f:
        json.dump(dict(extra, generated=data["generated"]), f, separators=(",", ":"))
    with open(os.path.join(os.path.dirname(out) or ".", "company-data.json"), "w") as f:
        json.dump(dict(company_extra, generated=data["generated"]), f, separators=(",", ":"))
    return {k: len(v) for k, v in dict(data, **extra, **company_extra).items() if isinstance(v, (list, dict))}
