"""One-off probe: daily volume of market trades per alliance country (prints counts only, never the key)."""
import json, os, urllib.request, urllib.parse, datetime as dt
KEY = os.environ["WARERA_API_KEY"]
B = "https://api2.warera.io/trpc/"
def call(proc, inp):
    r = urllib.request.Request(B + proc + "?input=" + urllib.parse.quote(json.dumps(inp)), headers={"X-API-Key": KEY, "User-Agent": "wartrack-probe"})
    return json.load(urllib.request.urlopen(r, timeout=30))["result"]["data"]
cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)).isoformat().replace("+00:00", "Z")
for name, cid in (("Ireland", "6813b6d446e731854c7ac7fe"), ("Mexico", "6813b6d446e731854c7ac7f8")):
    n = money = pages = 0; cur = None; other = 0
    while pages < 40:
        d = call("transaction.getPaginatedTransactions", {"countryId": cid, "transactionType": "trading", "limit": 100, **({"cursor": cur} if cur else {})})
        pages += 1
        stop = False
        for t in d["items"]:
            if t["createdAt"] < cut: stop = True; break
            n += 1; money += t.get("money") or 0
            if t.get("buyerCountryId") != cid: other += 1
        cur = d.get("nextCursor")
        if stop or not cur or not d["items"]: break
    print(f"VOLUME {name}: {n} trades in 24h, value {money:.0f}, pages {pages}, buyer elsewhere {other}")
