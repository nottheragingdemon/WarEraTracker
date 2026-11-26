"""One-off: print the shape of country money transfer transactions (no secrets are printed)."""
import json, os, sys
from wartrack.api import Client
c = Client()
ids = {x["_id"]: x.get("name") for x in c.call("country.getAllCountries")}
ie = [k for k, v in ids.items() if v == "Ireland"][0]
for params in ({"countryId": ie}, {"countryId": ie, "transactionType": "countryMoneyTransfer"}, {"transactionType": "countryMoneyTransfer"}):
    try:
        d = c.call("transaction.getPaginatedTransactions", limit=3, **params)
        print("PARAMS", params, "->", json.dumps(d)[:1500])
    except Exception as e:
        print("PARAMS", params, "ERROR", str(e)[:300])
