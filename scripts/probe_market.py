"""One-off probe: which transaction types exist and what a market sale looks like (prints structure, never the key)."""
import json, os, urllib.request, urllib.parse
KEY = os.environ["WARERA_API_KEY"]
B = "https://api2.warera.io/trpc/"
def call(proc, inp):
    r = urllib.request.Request(B + proc + "?input=" + urllib.parse.quote(json.dumps(inp)), headers={"X-API-Key": KEY, "User-Agent": "wartrack-probe"})
    try:
        return json.load(urllib.request.urlopen(r, timeout=30))
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")
IE = "6813b6d446e731854c7ac7fe"   # Ireland
bad = call("transaction.getPaginatedTransactions", {"countryId": IE, "transactionType": "zzz", "limit": 1})
print("INVALID TYPE ERROR:", json.dumps(bad)[:1500])
seen = set()
all_ = call("transaction.getPaginatedTransactions", {"countryId": IE, "limit": 100})
items = (all_.get("result") or {}).get("data", {}).get("items", [])
print("ANY TYPE: got", len(items), "error" if "error" in all_ else "")
for t in items:
    ty = t.get("transactionType")
    if ty not in seen:
        seen.add(ty)
        print("TYPE", ty, "->", json.dumps({k: (v if not isinstance(v, (dict, list)) else "<%s>" % type(v).__name__) for k, v in t.items()})[:700])
for ty in ("itemMarket", "trading", "market", "marketSale", "itemTrading", "tradeOrder"):
    r = call("transaction.getPaginatedTransactions", {"countryId": IE, "transactionType": ty, "limit": 3})
    print("TRY", ty, json.dumps(r)[:600])
