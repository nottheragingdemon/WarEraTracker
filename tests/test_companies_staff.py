"""Companies: located by the daily index (any owner), refreshed hourly in alliance host countries, with employees and wages."""
import unittest

from wartrack.stages import economy as EC
from wartrack import db as dbm


class Scope:
    members = ["c1"]


class Fake:
    n = 0
    ALL = {"k1": ("r1", "u1"), "k2": ("r1", "u2"), "k3": ("r9", "u1"), "k4": ("r1", "u3")}

    def call(self, proc, perPage=100, cursor=None):
        assert proc == "company.getCompanies"   # the global list, two ids per page here
        ids, i = list(self.ALL), int(cursor or 0)
        return {"items": ids[i:i + 2], "nextCursor": str(i + 2) if i + 2 < len(ids) else None}

    def map(self, fn, xs, workers=None):
        return [fn(x) for x in xs]

    def lookup_users(self, ids):
        return {u: {"username": u.upper(), "country": {"u1": "c1", "u2": "x9", "u3": "c1"}[u]} for u in ids}

    def batch_many(self, lists, official=False):
        out = []
        for l in lists:
            res = []
            for proc, inp in l:
                cid = inp.get("companyId")
                if proc == "company.getById":
                    reg, own = self.ALL[cid]
                    res.append({"name": cid, "user": own, "itemCode": "fish", "region": reg, "estimatedValue": 10,
                                **({"disabledAt": "2026-11-01"} if cid == "k4" else {})})
                elif proc == "employee.getCompanyEstimate":
                    res.append({"wageCost": 0.5, "managerCost": 0.1} if cid == "k1" else None)
                elif proc == "employee.getCompanyEmployees":
                    res.append([{"wage": 0.2}, {"wage": 0.3}] if cid == "k1" else [{"wage": 0.05}])
            out.append(res)
        return out


class CompanyTests(unittest.TestCase):
    def setUp(self):   # no agreements file: every owner in the alliance's countries is followed
        from wartrack.stages import common
        self._ag, common.AGREEMENTS_FILE = common.AGREEMENTS_FILE, "/nonexistent/agreements.json"

    def tearDown(self):
        from wartrack.stages import common
        common.AGREEMENTS_FILE = self._ag

    def test_index_then_hourly(self):
        db = dbm.connect(":memory:")
        db.execute("INSERT INTO region_now(region,name,country) VALUES('r1','Home','c1'),('r9','Away','c9')")
        f = Fake()
        EC.collect_companies(f, db, Scope())          # no index yet: nothing happens
        self.assertEqual(db.execute("SELECT COUNT(*) FROM companies").fetchone()[0], 0)
        EC.collect_company_index(f, db, Scope())
        self.assertEqual(db.execute("SELECT COUNT(*) FROM company_loc").fetchone()[0], 4)
        EC.collect_companies(f, db, Scope())
        rows = {r["id"]: (r["owner_country"], r["workers"], r["wages"]) for r in db.execute("SELECT * FROM companies")}
        self.assertEqual(rows, {"k1": ("c1", 2, 0.5), "k2": ("x9", 1, 0.05)})   # k2: non-alliance owner kept; k3 elsewhere, k4 disabled
        snaps = {(r["host"], r["owner_country"]): (r["companies"], r["workers"]) for r in db.execute("SELECT * FROM wage_snap3")}
        self.assertEqual(snaps, {("c1", "c1"): (1, 2), ("c1", "x9"): (1, 1)})
        Fake.ALL = {k: v for k, v in Fake.ALL.items() if k != "k2"}        # k2 closes: the next index run drops it
        try:
            EC.collect_company_index(f, db, Scope())
            EC.collect_companies(f, db, Scope())
        finally:
            Fake.ALL["k2"] = ("r1", "u2")
        self.assertEqual(sorted(r[0] for r in db.execute("SELECT id FROM companies")), ["k1"])


    def test_agreements_limit_owners(self):
        import json, os, tempfile
        from wartrack.stages import common
        db = dbm.connect(":memory:")
        db.execute("INSERT INTO region_now(region,name,country) VALUES('r1','Home','c1'),('r9','Away','c9')")
        db.execute("INSERT INTO country_tax(country,name) VALUES('c1','Hostland'),('x9','Partnerland'),('c9','Elsewhere')")
        path = os.path.join(tempfile.mkdtemp(), "agreements.json")
        json.dump({"agreements": {"Hostland": ["Partnerland"]}}, open(path, "w"))
        common.AGREEMENTS_FILE = path
        self.assertEqual(common.tax_agreements(db), {"c1": {"x9"}})
        f = Fake()
        EC.collect_company_index(f, db, Scope())
        EC.collect_companies(f, db, Scope())
        rows = {r["id"]: r["owner_country"] for r in db.execute("SELECT id, owner_country FROM companies")}
        self.assertEqual(rows, {"k2": "x9"})   # only the agreed country's citizens' company in the host


if __name__ == "__main__":
    unittest.main()
