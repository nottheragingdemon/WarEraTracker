"""Export the database to a compact data.json for the dashboard page (no network access needed)."""
import json, datetime as dt

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
    country_now = {str(E("country", r["country"])): [r["money"], r["wealth"], r["wealth_rank"], r["population"], r["development"]]
                   for r in db.execute("SELECT * FROM country_now")}
    wealth = [[E("user", r["eid"]), E("country", r["country"]), E("mu", r["mu"]), r["value"], r["rank"]]
              for r in db.execute("SELECT * FROM wealth_now ORDER BY value DESC")]
    transfers = [[r["ts"], E("country", r["sender"]), E("country", r["receiver"]), r["money"]]
                 for r in db.execute("SELECT * FROM transfers ORDER BY ts DESC")]
    regions_now = {r["region"]: [r["name"], E("country", r["country"]), r["emp"], r["mgr"], r["companies"], r["employees"]]
                   for r in db.execute("SELECT * FROM region_now")}
    country_tax = {str(E("country", r["country"])): [r["income"], r["manager"]] for r in db.execute("SELECT * FROM country_tax")}
    wage_hist = [[r["region"], E("country", r["owner_country"]), r["t"], r["companies"], r["workers"], r["wages"], r["mgr"] or 0]
                 for r in db.execute("SELECT * FROM wage_snap ORDER BY t")]
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
    data = {"v": 2, "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "since": since,
            "ents": ents, "battles": battles, "stats": stats, "orders": orders, "bounty": bounty, "contracts": contracts,
            "alliances": alliances, "relMu": rel_mu, "relUser": rel_user, "taxHist": tax_history(db), "companies": companies, "companiesAt": companies_at,
            "regionsNow": regions_now, "countryNow": country_now, "transfers": transfers, "wealthNow": wealth, "countryTax": country_tax,
            "wageHist": wage_hist, "rateHist": rate_hist, "runs": runs}
    with open(out, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    return {k: len(v) for k, v in data.items() if isinstance(v, (list, dict))}
