"""One-off probe: what employee.getCompanyEmployees returns (structure and counts only, never the key)."""
import json, os, urllib.request, urllib.parse
KEY = os.environ["WARERA_API_KEY"]
B = "https://api2.warera.io/trpc/"
def get(url):
    r = urllib.request.Request(url, headers={"X-API-Key": KEY, "User-Agent": "wartrack-probe"})
    try:
        return json.load(urllib.request.urlopen(r, timeout=30))
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")
for cid in ("69eb773552d6d96dc6d7361b", "6abd713fe448afb5ae87bea3"):
    for inp in ({"companyId": cid}, {"companyId": cid, "limit": 100}):
        d = get(B + "employee.getCompanyEmployees?input=" + urllib.parse.quote(json.dumps(inp)))
        print("INPUT", list(inp), "->", json.dumps(d)[:900])
    e = get(B + "employee.getCompanyEstimate?input=" + urllib.parse.quote(json.dumps({"companyId": cid})))
    print("ESTIMATE", json.dumps(e)[:500])
b = get(B + "employee.getCompanyEmployees?batch=1&input=" + urllib.parse.quote(json.dumps({"0": {"companyId": "69eb773552d6d96dc6d7361b"}, "1": {"companyId": "6abd713fe448afb5ae87bea3"}})))
print("BATCH", json.dumps(b)[:300])
