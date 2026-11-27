#!/usr/bin/env python3
"""15-minute battle check: posts new battles and ended battles involving the alliance to the Discord webhook.

Runs in this (public) repository; the hourly collector runs in the private back-end repository. It needs only the WarEra
API key and the webhook. Names (countries, regions) and the alliance's members come from site/data.json; which battles were
already announced is kept in state.json on the `battlecheck-state` branch (see .github/workflows/battle-check.yml).

    python3 scripts/battlecheck.py STATE_JSON            # check and post
    python3 scripts/battlecheck.py STATE_JSON --test     # post a test message
    python3 scripts/battlecheck.py --failure "TEXT"      # post a failure notice
"""
import datetime as dt, json, os, sys, time, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api2.warera.io/trpc/"
BATTLE_URL = "https://app.warera.io/battle/"
ALLIANCE = "The Emerald Accord"
MAX_LINES = 15


def call(proc, **params):
    params = {k: v for k, v in params.items() if v is not None}
    url = API + proc + ("?" + urllib.parse.urlencode({"input": json.dumps(params, separators=(",", ":"))}) if params else "")
    headers = {"User-Agent": "warera-battlecheck"}
    if os.environ.get("WARERA_API_KEY"):
        headers["X-API-Key"] = os.environ["WARERA_API_KEY"]
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                return json.loads(r.read().decode())["result"]["data"]
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError):
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def pages(proc, max_pages=20, **params):
    cursor = None
    for _ in range(max_pages):
        d = call(proc, cursor=cursor, **params)
        items = d["items"] if isinstance(d, dict) else d
        yield from items
        cursor = d.get("nextCursor") if isinstance(d, dict) else None
        if not cursor or not items:
            return


def post(text):
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        print("ALERT_WEBHOOK_URL not set; would post:\n" + text); return
    body = json.dumps({"content": text[:1900]}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "warera-battlecheck"}), timeout=20).read()


def fmt(x):
    x = x or 0
    return f"{x / 1e6:.1f}M" if abs(x) >= 1e6 else f"{x / 1e3:.0f}k" if abs(x) >= 1e3 else f"{x:.0f}"


STALE_HOURS = float(os.environ.get("STALE_HOURS", "3"))


def stale_check(data, state, now=None):
    """Return a message when data.json is older than STALE_HOURS (once per outage), or a recovery message; updates state."""
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        age = (now - dt.datetime.fromisoformat(data["generated"])).total_seconds() / 3600
    except (KeyError, ValueError, TypeError):
        return None
    if age > STALE_HOURS and not state.get("stale_alert"):
        state["stale_alert"] = now.isoformat(timespec="seconds")
        return f"⏰ The data on the site is {age:.1f} hours old (last update {data['generated'][:16].replace('T', ' ')} UTC). The hourly back-end refresh in WarEraTracker-backend may have stopped."
    if age <= STALE_HOURS and state.get("stale_alert"):
        state.pop("stale_alert")
        return "✅ Site data is updating again."
    return None


def main(state_path, test=False):
    if test:
        post("✅ Test alert from WarEra Ireland tools: the webhook works. New battles involving The Emerald Accord will appear here.")
        return
    data = json.load(open(os.path.join(ROOT, "site", "data.json")))
    ents = data["ents"]
    names = {(e[0], e[1]): e[2] for e in ents if e[2]}
    name = lambda t, i: names.get((t, i)) or f"…{(i or '')[-6:]}"
    alliance_id, members = None, set()
    for a, m in (data.get("alliances") or {}).items():
        if ents[int(a)][2] == ALLIANCE:
            alliance_id, members = ents[int(a)][1], {ents[c][1] for c in m}
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    note = stale_check(data, state)
    if note:
        try:
            post(note)
        except Exception as e:
            print(f"could not send the stale-data notice: {e}")
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).isoformat()[:19]
    extra = {"allianceId": alliance_id} if alliance_id else {}
    battles = {b["_id"]: b for b in pages("battle.getBattles", isActive=True, limit=100, **extra)}
    for b in pages("battle.getBattles", isActive=False, limit=100, **extra):
        if b["createdAt"] < since:
            break
        battles[b["_id"]] = b
    battles = {k: b for k, b in battles.items() if not members or (b["attacker"].get("country") in members or b["defender"].get("country") in members)}

    def line(b):
        return f"{name('country', b['attacker'].get('country'))} vs {name('country', b['defender'].get('country'))} in {name('region', b['defender'].get('region'))}"

    out = []
    last_new, last_end = state.get("battle_created"), state.get("battle_ended")
    if last_new is not None:
        for b in sorted(battles.values(), key=lambda x: x["createdAt"]):
            if b["createdAt"] > last_new:
                out.append(f"⚔️ New battle: {line(b)} ({b['createdAt'][:16].replace('T', ' ')} UTC)\n{BATTLE_URL}{b['_id']}")
    if last_end is not None:
        for b in sorted((x for x in battles.values() if x.get("endedAt")), key=lambda x: x["endedAt"]):
            if b["endedAt"] > last_end:
                att, dfn = b["attacker"].get("country"), b["defender"].get("country")
                won = b.get("wonBy")
                winner = name("country", att) if won == "attacker" else name("country", dfn) if won == "defender" else None
                ours = "attacker" if att in members else "defender" if dfn in members else None
                both = att in members and dfn in members
                head = ("✅ Battle won" if won == ours else "❌ Battle lost") if winner and ours and not both else "🏁 Battle ended"
                res = f"{winner} won" if winner else "no winner recorded"
                ad, dd = b["attacker"].get("damages"), b["defender"].get("damages")
                tail = " · ".join(x for x in (res, f"damage {fmt(ad)} vs {fmt(dd)}" if ad or dd else "") if x)
                out.append(f"{head}: {line(b)}: {tail}\n{BATTLE_URL}{b['_id']}")
    if out:
        more = len(out) - MAX_LINES
        post("\n".join(out[:MAX_LINES]) + (f"\n…and {more} more" if more > 0 else ""))
    new_mark = max((b["createdAt"] for b in battles.values()), default=last_new)
    end_mark = max((b["endedAt"] for b in battles.values() if b.get("endedAt")), default=last_end)
    state.update({"battle_created": max(filter(None, [last_new, new_mark]), default=None),
                  "battle_ended": max(filter(None, [last_end, end_mark]), default=None),
                  "checked": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
    json.dump(state, open(state_path, "w"), indent=1)
    print(f"battle check: {len(battles)} battles seen, {len(out)} lines posted")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--failure":
        try:
            post("⚠️ " + sys.argv[2])
        except Exception as e:   # a broken webhook must not hide the original failure
            print(f"could not send the failure notice: {e}")
        sys.exit(0)
    main(sys.argv[1] if len(sys.argv) > 1 else "state.json", "--test" in sys.argv)
