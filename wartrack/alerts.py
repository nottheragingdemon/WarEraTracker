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


def _ended_line(db, b, members):
    att, dfn = _name(db, "country", b["att_country"]), _name(db, "country", b["def_country"])
    won = b["won_by"]
    winner = att if won == "attacker" else dfn if won == "defender" else None
    ours = "attacker" if b["att_country"] in members else "defender" if b["def_country"] in members else None
    both = b["att_country"] in members and b["def_country"] in members
    if winner and ours and not both:
        head = "✅ Battle won" if won == ours else "❌ Battle lost"
    else:
        head = "🏁 Battle ended"
    res = f"{winner} won" if winner else "no winner recorded"
    dmg = f"damage {_fmt(b['att_damage'])} vs {_fmt(b['def_damage'])}" if b["att_damage"] or b["def_damage"] else ""
    tail = " · ".join(x for x in (res, dmg) if x)
    return f"{head}: {_battle_line(db, b)}: {tail}\n{BATTLE_URL}{b['id']}"


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
        "battle_ended": max((b["ended_at"] for b in battles.values() if b["ended_at"]), default=""),
    }
    last = {k: _state(db, k) for k in marks}
    lines = []

    # 1) new battles
    if last["battle_created"] is not None:
        for b in sorted(battles.values(), key=lambda x: x["created_at"]):
            if b["created_at"] > last["battle_created"]:
                lines.append(f"⚔️ New battle: {_battle_line(db, b)} ({b['created_at'][:16].replace('T', ' ')} UTC)\n{BATTLE_URL}{b['id']}")

    # 2) battles that ended, with the result for the alliance
    if last["battle_ended"] is not None:
        for b in sorted((x for x in battles.values() if x["ended_at"]), key=lambda x: x["ended_at"]):
            if b["ended_at"] > last["battle_ended"]:
                lines.append(_ended_line(db, b, members))

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


def _f1(x):
    """one decimal for small figures (bounty per 1M), compact form for big ones"""
    x = float(x or 0)
    return f"{x:,.1f}" if abs(x) < 1000 else _fmt(x)


def _esc(text):
    """Discord markdown would turn _name_ or *name* into italics: escape the characters that matter"""
    return "".join("\\" + ch if ch in "_*~`|>\\" else ch for ch in str(text))


MEDALS = ["🥇", "🥈", "🥉", "4.", "5."]


def _ranked(rows):
    """[(label, value text)] -> numbered lines with medals"""
    return [f"{MEDALS[i]} {label} — **{val}**" for i, (label, val) in enumerate(rows)]


def _totals(db, scope, start, end):
    """battles, alliance damage, transfers and citizen donations between two ISO times"""
    members = list(scope.members) if scope and scope.members else []
    cond, args = scope.battle_sql("b") if scope else ("1=1", [])
    mem = ",".join("?" * len(members)) or "''"
    w = f"{cond} AND b.created_at>=? AND b.created_at<?"
    t = {"battles": db.execute(f"SELECT COUNT(*) FROM battles b WHERE {w}", (*args, start, end)).fetchone()[0]}
    t["damage"] = db.execute(f"""SELECT COALESCE(SUM(s.value),0) FROM battle_stat s JOIN battles b ON b.id=s.battle_id
        WHERE s.etype='country' AND s.kind='damage' AND s.eid IN ({mem}) AND {w}""", (*members, *args, start, end)).fetchone()[0]
    t["transfers"] = db.execute(f"SELECT COALESCE(SUM(money),0) FROM transfers WHERE ts>=? AND ts<? AND sender IN ({mem}) AND receiver IN ({mem})",
                                (start, end, *members, *members)).fetchone()[0]
    t["donations"] = db.execute(f"SELECT COALESCE(SUM(money),0) FROM donations WHERE ts>=? AND ts<? AND country IN ({mem}) AND donor_country=country",
                                (start, end, *members)).fetchone()[0]
    return t


def _change(cur, prev):
    if not prev:
        return "(new)" if cur else ""
    pct = (cur - prev) / prev * 100
    return f"({'↑' if pct > 0.5 else '↓' if pct < -0.5 else '→'} {abs(pct):.0f}%)"


def _build(spent, eco):
    if not spent:
        return None
    share = eco / spent
    return "War" if share <= 0.20 else "Eco" if share > 0.50 else "Hybrid"


def _efficiency_lines(db, members, now, pname, cname):
    """Most efficient players (wealth gained per 1M damage over the last 7 days, 1M+ damage) and the build mix."""
    import datetime as dt
    if not members:
        return []
    mem = ",".join("?" * len(members))
    lo, today = (now.date() - dt.timedelta(days=7)).isoformat(), now.date().isoformat()
    rows = db.execute(f"""SELECT p.eid, p.country, p.wealth, p.dmg_total, p.dmg_week, s.spent, s.eco,
        (SELECT o.wealth FROM player_snap o WHERE o.eid=p.eid AND o.day>=? AND o.day<? ORDER BY o.day LIMIT 1) w0,
        (SELECT o.dmg_total FROM player_snap o WHERE o.eid=p.eid AND o.day>=? AND o.day<? ORDER BY o.day LIMIT 1) d0
        FROM player_now p LEFT JOIN player_skill s ON s.eid=p.eid WHERE p.country IN ({mem})""", (lo, today, lo, today, *members)).fetchall()
    if not rows:
        return []
    hist = any(r["w0"] is not None for r in rows)
    scored, mix = [], {"War": 0, "Hybrid": 0, "Eco": 0}
    for r in rows:
        dmg = (r["dmg_total"] - r["d0"]) if r["d0"] is not None else r["dmg_week"]
        if not dmg or dmg < 1e6:
            continue
        b = _build(r["spent"], r["eco"])
        if b:
            mix[b] += 1
        val = ((r["wealth"] - r["w0"]) if hist and r["w0"] is not None else (r["wealth"] if not hist else None))
        if val is not None:
            scored.append((val / (dmg / 1e6), r, b))
    out = ["**⚖️ Player efficiency** (1M+ damage)", f"Builds: War **{mix['War']}** · Hybrid **{mix['Hybrid']}** · Eco **{mix['Eco']}**"]
    if scored:
        out.append("Most " + ("wealth gained" if hist else "wealth") + " per 1M damage:")
        out += _ranked([(f"{pname(r['eid'])} ({cname(r['country'])}, {b or '?'})", _f1(v) if abs(v) < 1000 else _fmt(v))
                        for v, r, b in sorted(scored, key=lambda x: -x[0])[:5]])
    return out


def digest_text(db, scope, days=7, now=None):
    """The weekly summary as Discord-flavoured markdown: battles, damage and bounty by country and player, transfers, donations."""
    import datetime as dt
    now = now or dt.datetime.now(dt.timezone.utc)
    start = now - dt.timedelta(days=days)
    since = start.isoformat(timespec="seconds").replace("+00:00", "Z")
    members = list(scope.members) if scope and scope.members else []
    cond, args = scope.battle_sql("b") if scope else ("1=1", [])
    win = f"{cond} AND b.created_at>=?"
    wargs = [*args, since]
    mem = ",".join("?" * len(members)) or "''"
    n = db.execute(f"SELECT COUNT(*) FROM battles b WHERE {win}", wargs).fetchone()[0]
    day = lambda d: f"{d.day} {d.strftime('%b')}"
    out = ["📊 **Weekly digest · The Emerald Accord**",
           f"📅 {day(start)} – {day(now)} {now.year} (UTC)"]
    z = lambda d: d.isoformat(timespec="seconds").replace("+00:00", "Z")
    cur = _totals(db, scope, z(start), z(now))
    prev = _totals(db, scope, z(start - dt.timedelta(days=days)), z(start))
    have_prev = db.execute("SELECT COUNT(*) FROM battles WHERE created_at<?", (z(start),)).fetchone()[0] > 0
    out += ["", "**📈 This week" + (" vs last week**" if have_prev else "**")]
    for icon, label, key, f in (("⚔️", "Battles", "battles", str), ("💥", "Alliance damage", "damage", _fmt),
                                ("🔁", "Transfers between nations", "transfers", _fmt), ("🎁", "Citizen donations", "donations", _fmt)):
        out.append(f"{icon} {label}: **{f(cur[key])}** {_change(cur[key], prev[key]) if have_prev else ''}".rstrip())

    def per_entity(etype, extra_join="", extra_cond="", extra_args=()):
        rows = db.execute(f"""SELECT s.eid, s.kind, SUM(s.value) v FROM battle_stat s JOIN battles b ON b.id=s.battle_id {extra_join}
            WHERE s.etype=? AND {win} {extra_cond} GROUP BY s.eid, s.kind""", (etype, *wargs, *extra_args)).fetchall()
        d = {}
        for r in rows:
            d.setdefault(r["eid"], {"damage": 0.0, "money": 0.0})[r["kind"]] = r["v"]
        return d
    cname = lambda k: _esc(_name(db, "country", k))
    pname = lambda k: _esc(_name(db, "user", k))
    cs = {k: v for k, v in per_entity("country").items() if k in members}
    if cs:
        top = sorted(cs.items(), key=lambda kv: -kv[1]["damage"])[:5]
        out += ["", "**🏆 Top countries by damage**"] + _ranked([(cname(k), _fmt(v["damage"])) for k, v in top])
    ps = per_entity("user", "JOIN users u ON u.id=s.eid", f"AND u.country IN ({mem})", members)
    topd = sorted(ps.items(), key=lambda kv: -kv[1]["damage"])[:5]
    if topd:
        out += ["", "**🎯 Most damage · players**"] + _ranked([(pname(k), _fmt(v["damage"])) for k, v in topd])
    best_c = sorted(((k, v["money"] / (v["damage"] / 1e6)) for k, v in cs.items() if v["damage"] >= 1e6), key=lambda kv: -kv[1])[:3]
    best_p = sorted(((k, v["money"] / (v["damage"] / 1e6)) for k, v in ps.items() if v["damage"] >= 1e6), key=lambda kv: -kv[1])[:5]
    if best_c or best_p:
        out += ["", "**💰 Top bounty per 1M damage**"]
        if best_c:
            out.append("Countries: " + "  ·  ".join(f"{cname(k)} **{_f1(p)}**" for k, p in best_c))
        if best_p:
            out.append("Players (1M+ damage):")
            out += _ranked([(pname(k), _f1(p)) for k, p in best_p])
    eff = _efficiency_lines(db, members, now, pname, cname)
    if eff:
        out += [""] + eff
    if members:
        q = f"FROM transfers WHERE ts>=? AND sender IN ({mem}) AND receiver IN ({mem})"
        tr = db.execute(f"SELECT COUNT(*) n, COALESCE(SUM(money),0) m {q}", (since, *members, *members)).fetchone()
        big = db.execute(f"SELECT sender, receiver, money {q} ORDER BY money DESC LIMIT 1", (since, *members, *members)).fetchone()
        out += ["", "**🔁 Transfers & 🎁 donations**", f"**{tr['n']}** transfers between alliance nations"]
        if big:
            out[-1] += f" · largest {cname(big['sender'])} → {cname(big['receiver'])} **{_fmt(big['money'])}**"
        dn = db.execute(f"SELECT COUNT(DISTINCT donor) n FROM donations WHERE ts>=? AND country IN ({mem}) AND donor_country=country", (since, *members)).fetchone()
        out.append(f"**{dn['n']}** citizens donated to their own nation")
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
