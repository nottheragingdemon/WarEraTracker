"""Webhook alerts (Discord / Slack-compatible): new battles, new contracts and new bounties tied to the tracked alliance's battles.

Set ALERT_WEBHOOK_URL. The first run only records a starting point (nothing is sent), so enabling alerts never spams old events.
ALERT_BOUNTY_MIN (default 10000): smallest bounty (new entry) or bounty increase that counts as a posting.
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


def _battle_line(db, b):
    return f"{_name(db, 'country', b['att_country'])} vs {_name(db, 'country', b['def_country'])} in {_name(db, 'region', b['def_region'])}"


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
        "contract_created": db.execute("SELECT MAX(created_at) m FROM contracts").fetchone()["m"] or "",
        "bounty_ts": db.execute("SELECT MAX(ts) m FROM bounty_snap").fetchone()["m"] or "",
    }
    last = {k: _state(db, k) for k in marks}
    lines = []

    # 1) new battles
    if last["battle_created"] is not None:
        for b in sorted(battles.values(), key=lambda x: x["created_at"]):
            if b["created_at"] > last["battle_created"]:
                lines.append(f"⚔️ New battle: {_battle_line(db, b)} ({b['created_at'][:16].replace('T', ' ')} UTC)")

    # 2) new contracts posted for a tracked battle, grouped per battle so busy battles don't flood the channel
    if last["contract_created"] is not None:
        per = {}
        for c in db.execute("SELECT * FROM contracts WHERE created_at>? ORDER BY created_at", (last["contract_created"],)):
            if c["battle_id"] in battles:
                per.setdefault(c["battle_id"], []).append(c)
        for bid, cs in per.items():
            budget = sum(c["budget"] or 0 for c in cs)
            top = max(cs, key=lambda c: c["budget"] or 0)
            n = len(cs)
            lines.append(f"📜 {n} new contract{'s' if n > 1 else ''} in {_battle_line(db, battles[bid])}: total budget {budget:,.0f}, "
                         f"largest {top['budget'] or 0:,.0f} for {_name(db, 'country', top['for_country'])} ({top['side']}, min damage {top['min_damage'] or 0:,.0f})")

    # 3) bounty postings (a new ranking entry, or a rise, of at least ALERT_BOUNTY_MIN) on players, MUs and countries of the alliance
    if last["bounty_ts"] is not None and marks["bounty_ts"] > last["bounty_ts"]:
        newest = marks["bounty_ts"]
        prev_ts = db.execute("SELECT MAX(ts) m FROM bounty_snap WHERE ts<?", (newest,)).fetchone()["m"]
        if prev_ts:
            mn = float(os.environ.get("ALERT_BOUNTY_MIN", 10000))
            mu_country = {r["id"]: r["country"] for r in db.execute("SELECT id,country FROM mus")}
            old = {(r["rtype"], r["eid"]): r["value"] for r in db.execute("SELECT rtype,eid,value FROM bounty_snap WHERE ts=?", (prev_ts,))}
            active = [b for b in battles.values() if b["is_active"]]
            found = []
            for r in db.execute("SELECT * FROM bounty_snap WHERE ts=?", (newest,)):
                t = r["rtype"]
                country = r["eid"] if t == "countryBounty" else (mu_country.get(r["eid"]) if t == "muBounty" else r["country"])
                if members and country not in members:
                    continue
                o = old.get((t, r["eid"]))
                inc = r["value"] - (o or 0)
                if inc >= mn:  # a new entry counts too when its value reaches the minimum
                    found.append((inc, r, country, o is None))
            found.sort(key=lambda x: -x[0])
            for inc, r, country, is_new in found[:8]:
                kind = {"userBounty": "player", "muBounty": "MU", "countryBounty": "country"}[r["rtype"]]
                ctx = next((b for b in active if country in (b["att_country"], b["def_country"])), None)
                lines.append(f"💰 {'New bounty' if is_new else 'Bounty up ' + format(inc, ',.0f')} on {kind} {_name(db, {'userBounty': 'user', 'muBounty': 'mu', 'countryBounty': 'country'}[r['rtype']], r['eid'])}"
                             f" ({_name(db, 'country', country)}): {r['value']:,.0f}" + (f" · active battle {_battle_line(db, ctx)}" if ctx else ""))
            if len(found) > 8:
                lines.append(f"💰 …and {len(found) - 8} more new bounties")

    if lines:
        extra = len(lines) - MAX_LINES
        post(url, "\n".join(lines[:MAX_LINES]) + (f"\n…and {extra} more" if extra > 0 else ""))
    for k, v in marks.items():  # a kind seen for the first time only records its baseline (nothing sent)
        if v and (last[k] is None or v > last[k]):
            _set(db, k, v)
    db.commit()
    C.log(f"alerts: {len(lines)} lines sent")
