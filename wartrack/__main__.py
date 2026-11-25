import argparse, json, os, sys
from . import api, db as dbm, collect as C, report as R


def load_scope_cfg():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scope.json")
    return json.load(open(path)) if os.path.exists(path) else {}


def main():
    cfg = load_scope_cfg()
    p = argparse.ArgumentParser(prog="wartrack", description="WarEra orders / damage / bounty / contract tracker")
    p.add_argument("--db", default=os.environ.get("WARTRACK_DB", "wartrack.sqlite"))
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="pull data from the API into the local database")
    c.add_argument("--since", default=cfg.get("since", "3d"), help="e.g. 3d, 12h, 2026-11-20 (battles/contracts created after); default from scope.json")
    c.add_argument("--alliance", default=cfg.get("alliance"), help="only battles involving this alliance's countries (default from scope.json); use 'all' for no limit")
    c.add_argument("--what", default="alliances,regions,battles,damage,people,bounty,contracts,companies")
    c.add_argument("--damage-limit", type=int, help="max battles per level to fetch damage/money rankings for (newest first)")
    c.add_argument("--no-users", action="store_true", help="skip per-player damage (much faster)")
    c.add_argument("--user-pages", type=int, default=2, help="pages of 100 players per side per battle")
    c.add_argument("--player-limit", type=int, default=800, help="max new players to look up per run")
    c.add_argument("--bounty-top", type=int, default=200)

    sub.add_parser("alerts", help="send webhook alerts (new battles, bounty jumps); needs ALERT_WEBHOOK_URL")

    x = sub.add_parser("export", help="write data.json for the dashboard")
    x.add_argument("--since", default=cfg.get("since", "7d")); x.add_argument("--alliance", default=cfg.get("alliance")); x.add_argument("--out", default="site/data.json")
    x.add_argument("--user-top", type=int, default=150); x.add_argument("--no-names", action="store_true")

    r = sub.add_parser("report", help="query the database")
    r.add_argument("what", choices=["damage", "orders", "bounty", "contracts"])
    r.add_argument("--since", default="7d")
    r.add_argument("--until")
    r.add_argument("--alliance"); r.add_argument("--country"); r.add_argument("--mu"); r.add_argument("--user")
    r.add_argument("--by", default="auto", choices=["auto", "battle", "user", "mu", "country", "alliance"])
    r.add_argument("--top", type=int, default=20)
    r.add_argument("--csv", action="store_true")
    r.add_argument("--no-names", action="store_true", help="don't look up MU/player names over the API")
    a = p.parse_args()

    cl = api.Client(verbose=a.verbose)
    db = dbm.connect(a.db)
    if a.cmd == "collect":
        since = C.parse_when(a.since)
        what = set(a.what.split(","))
        if "alliances" in what: C.collect_alliances(cl, db)
        if "regions" in what: C.collect_regions(cl, db)
        scope = C.Scope(db, None if a.alliance in (None, "all") else a.alliance, since)
        if scope.active: C.log(f"scope: battles involving {a.alliance} ({len(scope.members)} countries) since {since[:10]}")
        if "battles" in what: C.collect_battles(cl, db, since, scope)
        if "damage" in what:
            lv = ("country", "mu") if a.no_users else C.LEVELS
            C.collect_stats(cl, db, lv, a.damage_limit, {"country": 2, "mu": 3, "user": a.user_pages}, scope)
        if "people" in what: C.collect_people(cl, db, a.player_limit, scope)
        if "bounty" in what: C.collect_bounty(cl, db, a.bounty_top, scope)
        if "contracts" in what: C.collect_contracts(cl, db, since, scope)
        if "companies" in what: C.collect_companies(cl, db, scope)
        print(f"done, {cl.n} API calls")
        return
    if a.cmd == "alerts":
        from . import alerts as AL
        AL.run(db, C.Scope(db, cfg.get("alliance"), C.parse_when(cfg.get("since", "7d")))); return
    R.load_countries(cl, db)
    if a.cmd == "export":
        from . import export as X
        print(X.export(db, a.out, C.parse_when(a.since), C.Scope(db, None if a.alliance in (None, "all") else a.alliance, C.parse_when(a.since)))); return
    f = R.Filters(C.parse_when(a.since), C.parse_when(a.until) if a.until else None)
    for k in ("alliance", "country", "mu", "user"):
        v = getattr(a, k)
        if v:
            setattr(f, k, R.resolve(cl, db, k, v))
    nm = lambda t, i: R.name_of(None if a.no_names else cl, db, t, i)

    def label(hdr, rows):
        t = hdr[0] if hdr[0] in ("user", "mu", "country") else None
        kind = {"battle": None}.get(hdr[0], t)
        if kind:
            rows = [(f"{nm(kind, x[0])} ({x[0][-6:]})", *x[1:]) if kind != "country" else (nm("country", x[0]), *x[1:]) for x in rows]
        return rows
    if a.what == "damage":
        h, rows, tot = R.damage(db, f, a.by, a.top); R.table(h, label(h, rows), tot, as_csv=a.csv)
    elif a.what == "orders":
        h, rows, tot = R.orders(db, f, a.top)
        rows = [(k, nm(k, i) if k != "country" else nm("country", i), s, n) for k, i, s, n in rows]
        R.table(h, rows, tot, as_csv=a.csv)
    elif a.what == "bounty":
        h, rows, tot = R.bounty(db, f, a.top)
        kind = {"userBounty": "user", "muBounty": "mu", "countryBounty": "country"}
        rows = [(r[0], nm(kind[r[0]], r[1]), *r[2:]) for r in rows]
        R.table(h, rows, tot, as_csv=a.csv)
    else:
        summ, detail = R.contracts(db, f)
        R.table(["status", "count", "budget", "payout"], summ, as_csv=a.csv)
        print()
        R.table(["id", "created", "status", "for_country", "side", "min_dmg", "budget", "payout", "winner_mu", "winner_user"],
                detail[:a.top], len(detail), as_csv=a.csv)


main()
