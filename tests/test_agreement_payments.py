"""Tax agreement payments: the host's treasury transfers to a partner are kept, even when the partner is outside the alliance."""
import json, os, tempfile, unittest

from wartrack import db as dbm
from wartrack.stages import common, money


class Scope:
    members = ["ie", "mx"]


class Fake:
    TX = {"ie": [{"_id": "t1", "createdAt": "2099-01-02T00:00:00Z", "sellerCountryId": "ie", "buyerCountryId": "uk", "money": 300},
                 {"_id": "t2", "createdAt": "2099-01-01T00:00:00Z", "sellerCountryId": "ie", "buyerCountryId": "mx", "money": 200},
                 {"_id": "t3", "createdAt": "2099-01-01T00:00:00Z", "sellerCountryId": "ie", "buyerCountryId": "zz", "money": 50}],
          "mx": []}

    def pages(self, proc, max_pages=1, countryId=None, **kw):
        return list(self.TX.get(countryId, []))

    def map(self, fn, xs, workers=None):
        return [fn(x) for x in xs]


class AgreementPaymentTests(unittest.TestCase):
    def setUp(self):
        self._ag = common.AGREEMENTS_FILE

    def tearDown(self):
        common.AGREEMENTS_FILE = self._ag

    def test_payments_to_partners(self):
        db = dbm.connect(":memory:")
        db.execute("INSERT INTO country_tax(country,name) VALUES('ie','Ireland'),('uk','United Kingdom'),('mx','Mexico'),('zz','Other')")
        path = os.path.join(tempfile.mkdtemp(), "agreements.json")
        json.dump({"agreements": {"Ireland": [{"country": "Mexico", "regions": "all"}, {"country": "United Kingdom", "regions": "all"}]}}, open(path, "w"))
        common.AGREEMENTS_FILE = path
        money.collect_transfers(Fake(), db, Scope(), days=100000)
        pay = sorted((r["partner"], r["money"]) for r in db.execute("SELECT * FROM agreement_payments"))
        self.assertEqual(pay, [("mx", 200), ("uk", 300)])                       # not the transfer to a non-partner
        self.assertEqual([r["id"] for r in db.execute("SELECT id FROM transfers")], ["t2"])   # members only, as before


if __name__ == "__main__":
    unittest.main()
