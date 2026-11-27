"""Military units, player names, bounty and wealth rankings, alliances."""
import os
import datetime as dt

from .common import log, now_iso


def collect_people(c, db, user_limit=800, scope=None):
    """MU list (names, country, members) and per-player country/name so filters can cascade."""
    every = float(os.environ.get("WARTRACK_PEOPLE_EVERY_H", "6"))   # the MU list changes slowly: refresh it every few hours, not every run
    last = db.execute("SELECT v FROM meta WHERE k='mu_list_at'").fetchone()
    have = db.execute("SELECT COUNT(*) FROM mu_members").fetchone()[0]
    fresh = last and have and (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(last["v"])).total_seconds() < every * 3600
    if fresh:
        log(f"people: MU list is less than {every:g} h old, kept")
    else:
        _refresh_mus(c, db)
    cond, cargs = scope.battle_sql("b") if scope else ("1=1", [])
    return _resolve_players(c, db, cond, cargs, user_limit)


def _refresh_mus(c, db):
    n = 0
    db.execute("DELETE FROM mu_members")
    for m in c.pages("mu.getManyPaginated", limit=100):
        n += 1
        db.execute("INSERT OR REPLACE INTO mus VALUES(?,?,?)", (m["_id"], m["name"], m.get("country")))
        db.execute("INSERT OR REPLACE INTO names VALUES('mu',?,?,NULL)", (m["_id"], m["name"]))
        for u in m.get("members", []):
            db.execute("INSERT OR IGNORE INTO mu_members VALUES(?,?)", (m["_id"], u))
    db.execute("INSERT OR REPLACE INTO meta VALUES('mu_list_at',?)", (now_iso(),))
    db.commit()
    log(f"people: {n} MUs, {db.execute('SELECT COUNT(*) FROM mu_members').fetchone()[0]} members")


def _resolve_players(c, db, cond, cargs, user_limit):
    todo = db.execute(f"""SELECT s.eid, SUM(s.value) v FROM battle_stat s JOIN battles b ON b.id=s.battle_id
        LEFT JOIN users u ON u.id=s.eid
        WHERE s.etype='user' AND s.kind='damage' AND (u.id IS NULL OR u.name IS NULL OR u.country IS NULL) AND {cond}
        GROUP BY s.eid ORDER BY v DESC LIMIT ?""", (*cargs, user_limit)).fetchall()
    for eid, u in c.lookup_users([r["eid"] for r in todo]).items():
        db.execute("INSERT OR REPLACE INTO users VALUES(?,?,?,?)", (eid, u.get("country"), u.get("mu"), u.get("username")))
        db.execute("INSERT OR REPLACE INTO names VALUES('user',?,?,NULL)", (eid, u.get("username")))
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
