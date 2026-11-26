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


def failure(text):
    """Post a failure notice (no database needed). Never raises: a broken webhook must not hide the original failure."""
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        C.log("alerts: ALERT_WEBHOOK_URL not set, failure notice not sent"); return
    try:
        post(url, "⚠️ " + text)
        C.log("alerts: failure notice sent")
    except Exception as e:
        C.log(f"alerts: could not send failure notice ({e})")


def skipped(db, stages):
    """Some collector stages gave up after API errors: tell the webhook, at most once every 6 hours."""
    db.execute("CREATE TABLE IF NOT EXISTS alert_state(k TEXT PRIMARY KEY, v TEXT)")
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    last = _state(db, "skipped_at")
    if last and now - dt.datetime.fromisoformat(last) < dt.timedelta(hours=6):
        return
    if os.environ.get("ALERT_WEBHOOK_URL"):
        failure("WarEra Tracker: these stages were skipped after API errors, so their data is not fresh: " + ", ".join(stages))
        _set(db, "skipped_at", now.isoformat(timespec="seconds")); db.commit()


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


def _fmt(x):
    x = float(x or 0)
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(x) >= lim:
            return f"{x / lim:.2f}{suf}"
    return f"{x:,.0f}"


def digest_text(db, scope, days=7, now=None):
    """The weekly summary: battles, damage and bounty by country and player, money transfers, citizen donations."""
    import datetime as dt
    now = now or dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    members = list(scope.members) if scope and scope.members else []
    cond, args = scope.battle_sql("b") if scope else ("1=1", [])
    win = f"{cond} AND b.created_at>=?"
    wargs = [*args, since]
    mem = ",".join("?" * len(members)) or "''"
    n = db.execute(f"SELECT COUNT(*) FROM battles b WHERE {win}", wargs).fetchone()[0]
    out = [f"📊 Weekly digest: The Emerald Accord, {since[:10]} to {now.date().isoformat()} (UTC)", f"Battles involving the alliance: {n}"]

    def per_entity(etype, extra_join="", extra_cond="", extra_args=()):
        rows = db.execute(f"""SELECT s.eid, s.kind, SUM(s.value) v FROM battle_stat s JOIN battles b ON b.id=s.battle_id {extra_join}
            WHERE s.etype=? AND {win} {extra_cond} GROUP BY s.eid, s.kind""", (etype, *wargs, *extra_args)).fetchall()
        d = {}
        for r in rows:
            d.setdefault(r["eid"], {"damage": 0.0, "money": 0.0})[r["kind"]] = r["v"]
        return d
    # countries of the alliance
    cs = {k: v for k, v in per_entity("country").items() if k in members}
    if cs:
        top = sorted(cs.items(), key=lambda kv: -kv[1]["damage"])[:5]
        out.append("Top countries by damage: " + "; ".join(f"{_name(db, 'country', k)} {_fmt(v['damage'])}" for k, v in top))
        best = sorted(((k, v["money"] / (v["damage"] / 1e6)) for k, v in cs.items() if v["damage"] >= 1e6), key=lambda kv: -kv[1])[:3]
        if best:
            out.append("Best bounty per 1M damage (countries): " + "; ".join(f"{_name(db, 'country', k)} {_fmt(p)}" for k, p in best))
    # players of the alliance's countries (at least 1M damage in the week)
    ps = per_entity("user", "JOIN users u ON u.id=s.eid", f"AND u.country IN ({mem})", members)
    ranked = sorted(((k, v["money"] / (v["damage"] / 1e6), v["damage"]) for k, v in ps.items() if v["damage"] >= 1e6), key=lambda x: -x[1])[:5]
    if ranked:
        out.append("Best bounty per 1M damage (players, 1M+ damage): " + "; ".join(f"{_name(db, 'user', k)} {_fmt(p)}" for k, p, _ in ranked))
    topd = sorted(ps.items(), key=lambda kv: -kv[1]["damage"])[:3]
    if topd:
        out.append("Most damage (players): " + "; ".join(f"{_name(db, 'user', k)} {_fmt(v['damage'])}" for k, v in topd))
    # money transfers between member countries
    if members:
        tr = db.execute(f"SELECT COUNT(*) n, COALESCE(SUM(money),0) m FROM transfers WHERE ts>=? AND sender IN ({mem}) AND receiver IN ({mem})", (since, *members, *members)).fetchone()
        line = f"Money transfers between alliance nations: {tr['n']} totalling {_fmt(tr['m'])}"
        big = db.execute(f"SELECT sender, receiver, money FROM transfers WHERE ts>=? AND sender IN ({mem}) AND receiver IN ({mem}) ORDER BY money DESC LIMIT 1", (since, *members, *members)).fetchone()
        if big:
            line += f" (largest: {_name(db, 'country', big['sender'])} → {_name(db, 'country', big['receiver'])} {_fmt(big['money'])})"
        out.append(line)
        dn = db.execute(f"SELECT COUNT(DISTINCT donor) n, COALESCE(SUM(money),0) m FROM donations WHERE ts>=? AND country IN ({mem}) AND donor_country=country", (since, *members)).fetchone()
        out.append(f"Citizen donations to their own nation: {_fmt(dn['m'])} from {dn['n']} citizens")
    return "\n".join(out)


def digest(db, scope, force=False):
    """Post the weekly digest (at most once every 6 days unless forced)."""
    import datetime as dt
    db.execute("CREATE TABLE IF NOT EXISTS alert_state(k TEXT PRIMARY KEY, v TEXT)")
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        C.log("alerts: ALERT_WEBHOOK_URL not set, digest skipped"); return
    now = dt.datetime.now(dt.timezone.utc)
    last = _state(db, "digest_at")
    if last and not force and now - dt.datetime.fromisoformat(last) < dt.timedelta(days=6):
        C.log(f"alerts: last digest was sent {last}, not sending another yet"); return
    post(url, digest_text(db, scope, now=now))
    _set(db, "digest_at", now.isoformat(timespec="seconds")); db.commit()
    C.log("alerts: weekly digest sent")
