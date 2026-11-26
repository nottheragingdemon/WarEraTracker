"""Webhook alerts (Discord / Slack-compatible): new battles involving the tracked alliance's countries.

Set ALERT_WEBHOOK_URL. The first run only records a starting point (nothing is sent), so enabling alerts never spams old events.
"""
import json, os, urllib.request
from . import collect as C

MAX_LINES = 15
BATTLE_URL = "https://app.warera.io/battle/"


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


def _battle_line(db, b):
    return f"{_name(db, 'country', b['att_country'])} vs {_name(db, 'country', b['def_country'])} in {_name(db, 'region', b['def_region'])}"


def test():
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        raise SystemExit("ALERT_WEBHOOK_URL is not set for this workflow")
    post(url, "✅ Test alert from WarEra Tracker: the webhook works. New battles involving The Emerald Accord will appear here.")
    C.log("alerts: test message sent")


def run(db, scope):
    db.execute("CREATE TABLE IF NOT EXISTS alert_state(k TEXT PRIMARY KEY, v TEXT)")
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        C.log("alerts: ALERT_WEBHOOK_URL not set, skipped"); return
    members = set(scope.members) if scope and scope.members else set()
    cond, args = scope.battle_sql("b") if scope else ("1=1", [])
    battles = {b["id"]: b for b in db.execute(f"SELECT * FROM battles b WHERE {cond}", args)}
    marks = {
        "battle_created": max((b["created_at"] for b in battles.values()), default=""),
    }
    last = {k: _state(db, k) for k in marks}
    lines = []

    # 1) new battles
    if last["battle_created"] is not None:
        for b in sorted(battles.values(), key=lambda x: x["created_at"]):
            if b["created_at"] > last["battle_created"]:
                lines.append(f"⚔️ New battle: {_battle_line(db, b)} ({b['created_at'][:16].replace('T', ' ')} UTC)\n{BATTLE_URL}{b['id']}")

    if lines:
        extra = len(lines) - MAX_LINES
        post(url, "\n".join(lines[:MAX_LINES]) + (f"\n…and {extra} more" if extra > 0 else ""))
    for k, v in marks.items():  # a kind seen for the first time only records its baseline (nothing sent)
        if v and (last[k] is None or v > last[k]):
            _set(db, k, v)
    db.commit()
    C.log(f"alerts: {len(lines)} lines sent")
