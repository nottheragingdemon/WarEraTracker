"""Webhook alerts (Discord / Slack-compatible): new in-scope battles and big bounty jumps on member countries.

Set ALERT_WEBHOOK_URL. The first run only records a starting point (nothing is sent), so enabling alerts never spams old events.
Tune with ALERT_BOUNTY_PCT (default 25) and ALERT_BOUNTY_MIN (default 20000, absolute increase).
"""
import json, os, urllib.request
from . import collect as C

MAX_LINES = 15


def _state(db, k, default=None):
    r = db.execute("SELECT v FROM alert_state WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def _set(db, k, v):
    db.execute("INSERT OR REPLACE INTO alert_state VALUES(?,?)", (k, v))


def _name(db, etype, eid):
    r = db.execute("SELECT name FROM names WHERE etype=? AND eid=?", (etype, eid)).fetchone()
    return (r["name"] if r and r["name"] else None) or f"…{(eid or '')[-6:]}"


def post(url, text):
    body = json.dumps({"content": text[:1900], "text": text[:1900]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "wartrack-alerts"})
    urllib.request.urlopen(req, timeout=20).read()


def run(db, scope):
    db.execute("CREATE TABLE IF NOT EXISTS alert_state(k TEXT PRIMARY KEY, v TEXT)")
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        C.log("alerts: ALERT_WEBHOOK_URL not set, skipped"); return
    members = sorted(scope.members) if scope and scope.members else []
    cond, args = scope.battle_sql("b") if scope else ("1=1", [])
    last_b = _state(db, "battle_created")
    last_t = _state(db, "bounty_ts")
    newest_b = db.execute(f"SELECT MAX(created_at) m FROM battles b WHERE {cond}", args).fetchone()["m"]
    newest_t = db.execute("SELECT MAX(ts) m FROM bounty_snap").fetchone()["m"]
    if last_b is None or last_t is None:  # first run: just set the baseline
        _set(db, "battle_created", newest_b or ""); _set(db, "bounty_ts", newest_t or ""); db.commit()
        C.log("alerts: baseline recorded, nothing sent"); return
    lines = []
    for b in db.execute(f"SELECT * FROM battles b WHERE {cond} AND b.created_at>? ORDER BY b.created_at", (*args, last_b)):
        reg = _name(db, "region", b["def_region"])
        lines.append(f"⚔️ New battle: {_name(db, 'country', b['att_country'])} vs {_name(db, 'country', b['def_country'])} in {reg} ({b['created_at'][:16].replace('T', ' ')} UTC)")
    pct = float(os.environ.get("ALERT_BOUNTY_PCT", 25)); mn = float(os.environ.get("ALERT_BOUNTY_MIN", 20000))
    if newest_t and newest_t > (last_t or ""):
        prev_ts = db.execute("SELECT MAX(ts) m FROM bounty_snap WHERE ts<?", (newest_t,)).fetchone()["m"]
        if prev_ts:
            cur = {r["eid"]: r["value"] for r in db.execute("SELECT eid,value FROM bounty_snap WHERE ts=? AND rtype='countryBounty'", (newest_t,))}
            old = {r["eid"]: r["value"] for r in db.execute("SELECT eid,value FROM bounty_snap WHERE ts=? AND rtype='countryBounty'", (prev_ts,))}
            for eid, v in cur.items():
                if members and eid not in members:
                    continue
                o = old.get(eid)
                if o and v - o >= mn and (v - o) / o * 100 >= pct:
                    lines.append(f"💰 Bounty on {_name(db, 'country', eid)} up {v - o:,.0f} (+{(v - o) / o * 100:.0f}%) to {v:,.0f}")
    if lines:
        extra = len(lines) - MAX_LINES
        text = "\n".join(lines[:MAX_LINES]) + (f"\n…and {extra} more" if extra > 0 else "")
        post(url, text)
    _set(db, "battle_created", newest_b or last_b); _set(db, "bounty_ts", newest_t or last_t); db.commit()
    C.log(f"alerts: {len(lines)} sent")
