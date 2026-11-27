"""Battles, per-battle damage and money rankings, mercenary contracts."""
import os
import json, datetime as dt

from .common import log, now_iso


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
        def fetch(r):   # all rankings of one battle; several battles are fetched at once
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
            return bid, rows
        done = 0
        for g in range(0, len(todo), 12):
            for bid, rows in c.map(fetch, todo[g:g + 12], workers=8):
                db.execute("DELETE FROM battle_stat WHERE battle_id=? AND etype IN (?,?)", (bid, level, "alliance" if level == "country" else level))
                db.executemany("INSERT OR REPLACE INTO battle_stat VALUES(?,?,?,?,?,?)", rows)
                db.execute("INSERT OR REPLACE INTO battle_fetch VALUES(?,?,?)", (bid, level, now_iso()))
                db.commit()
                done += 1
            log(f"  {level} {done}/{len(todo)} (api calls so far: {c.n})")


STATUSES = ["active", "won", "expiredNoBids", "expiredBattle", "expiredRound", "cancelled"]


def collect_contracts(c, db, since, scope=None):
    """Mercenary contracts since a date; with a scope, only those tied to an in-scope battle are kept."""
    keep_b = None
    if scope and scope.active:
        cond, cargs = scope.battle_sql("b")
        keep_b = {r[0] for r in db.execute(f"SELECT id FROM battles b WHERE {cond}", cargs)}
    n = seen = 0

    def fetch(st):   # one status list, newest first, down to `since`
        out = []
        for a in c.pages("mercenaryContractAuction.getPaginatedAuctions", status=st, limit=50):
            if a["createdAt"] < since:
                break
            out.append(a)
        return out
    # closed contracts rarely change: their lists (the long ones) are read every few hours, the active list every run
    every = float(os.environ.get("WARTRACK_CONTRACTS_FULL_H", "3"))
    last = db.execute("SELECT v FROM meta WHERE k='contracts_full_at'").fetchone()
    full = not last or (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(last["v"])).total_seconds() >= every * 3600
    statuses = STATUSES if full else ["active"]
    for found in c.map(fetch, statuses):   # the status lists are read in parallel, written one after another
        for a in found:
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
    if full:
        db.execute("INSERT OR REPLACE INTO meta VALUES('contracts_full_at',?)", (now_iso(),))
    db.commit()
    log(f"contracts: {n} stored ({seen} seen, {'all statuses' if full else f'active only; closed lists every {every:g} h'})")
