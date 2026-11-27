"""Player efficiency: daily wealth and damage snapshots and skill allocation."""
import json, datetime as dt

from .common import log, now_iso


ECO_SKILLS = ("companies", "energy", "management", "production")


def skill_points(level):
    """points spent to reach a skill level: 1 + 2 + ... + level (checked against spentSkillPoints)"""
    level = int(level or 0)
    return level * (level + 1) // 2


def collect_efficiency(c, db, scope=None, per_country=300, min_week=200_000):
    """Player efficiency: for each alliance country, the players with the most damage this week (game weekly ranking), down to
    200k damage (up to 300 a country, so the page's bottom 20 among the 1M+ damage players are covered as well as the top 20):
    wealth and damage totals snapshotted once per UTC day (so weekly changes can be computed) and their skill allocation."""
    members = list(scope.members) if scope and scope.members else []
    if not members:
        log("efficiency: no alliance scope, skipped"); return
    ts = now_iso()
    today = ts[:10]

    def top(country):
        out = []
        for e in c.pages("ranking.getRankingPage", rankingType="weeklyUserDamages", limit=50, max_pages=max(1, per_country // 50), countryId=country):
            if (e.get("value") or 0) < min_week:
                break
            out.append(e["user"])
        return out
    pool = {u for us in c.map(top, members) for u in us}
    week_ago = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=8)).date().isoformat()
    pool |= {r["eid"] for r in db.execute("SELECT DISTINCT eid FROM player_snap WHERE day>=?", (week_ago,))}   # keep histories going
    users = c.lookup_users(sorted(pool))
    db.execute("DELETE FROM player_now")
    kept = []
    for u, d in users.items():
        if d.get("country") not in members:
            continue
        rk = d.get("rankings") or {}
        wealth = (rk.get("userWealth") or {}).get("value") or 0
        total = (rk.get("userDamages") or {}).get("value") or (d.get("stats") or {}).get("damagesCount") or 0
        week = (rk.get("weeklyUserDamages") or {}).get("value") or 0
        db.execute("INSERT OR REPLACE INTO player_now VALUES(?,?,?,?,?,?,?,?)", (u, d["country"], d.get("mu"), d.get("username"), wealth, total, week, ts))
        db.execute("INSERT OR REPLACE INTO player_snap VALUES(?,?,?,?,?,?)", (u, today, wealth, total, week, ts))
        db.execute("INSERT INTO users(id,country,mu,name) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET country=excluded.country, mu=excluded.mu, name=excluded.name",
                   (u, d["country"], d.get("mu"), d.get("username")))
        db.execute("INSERT OR REPLACE INTO names VALUES('user',?,?,NULL)", (u, d.get("username")))
        kept.append((u, ((d.get("dates") or {}).get("lastSkillsResetAt")) or ""))
    # skills: fetched for new players, once a day, or right after the player reset them
    day_ago = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=23)).isoformat(timespec="seconds")
    have = {r["eid"]: (r["checked"], r["reset_at"] or "") for r in db.execute("SELECT eid, checked, reset_at FROM player_skill")}
    need = [u for u, reset in kept if u not in have or have[u][0] < day_ago or reset > have[u][1]]
    chunks = [need[i:i + 40] for i in range(0, len(need), 40)]
    for ch, res in zip(chunks, c.batch_many([[("user.getUserSkills", {"userId": u}) for u in ch] for ch in chunks])):
        for u, s in zip(ch, res):
            if not s or not s.get("skills"):
                continue
            lv = {k: int((v or {}).get("level") or 0) for k, v in s["skills"].items()}
            spent = (s.get("leveling") or {}).get("spentSkillPoints") or sum(skill_points(x) for x in lv.values())
            eco = sum(skill_points(lv.get(k)) for k in ECO_SKILLS)
            reset = ((s.get("dates") or {}).get("lastSkillsResetAt")) or ""
            old = db.execute("SELECT checked, spent, eco FROM player_skill WHERE eid=?", (u,)).fetchone()
            if old and (old["spent"], old["eco"]) != (spent, eco):   # the allocation changed: keep the previous one
                db.execute("INSERT OR REPLACE INTO player_skill_hist VALUES(?,?,?,?)", (u, old["checked"], old["spent"], old["eco"]))
            db.execute("INSERT OR REPLACE INTO player_skill VALUES(?,?,?,?,?,?)", (u, ts, reset, spent, eco, json.dumps(lv, separators=(",", ":"))))
    db.commit()
    log(f"efficiency: {len(kept)} players in {len(members)} countries, {len(need)} skill sets fetched")
