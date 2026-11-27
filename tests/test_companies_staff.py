"""Companies: worker counts come from employee.getCompanyEmployees (the company record no longer lists workers)."""
import unittest

from wartrack.stages import economy as EC
from wartrack import db as dbm


class Scope:
    members = ["c1"]


class Fake:
    n = 0

    def pages(self, proc, **kw):
        if proc == "user.getUsersByCountry":
            yield {"_id": "u1"}

    def map(self, fn, xs, workers=None):
        return [fn(x) for x in xs]

    def lookup_users(self, ids):
        return {u: {"username": "Ann", "country": "c1"} for u in ids}

    def batch_many(self, lists, official=False):
        out = []
        for l in lists:
            res = []
            for proc, inp in l:
                if proc == "company.getCompanies":
                    res.append({"items": ["k1", "k2"], "nextCursor": None})
                elif proc == "company.getById":
                    res.append({"name": inp["companyId"], "user": "u1", "itemCode": "fish", "region": "r1", "estimatedValue": 10})
                elif proc == "employee.getCompanyEstimate":
                    res.append({"wageCost": 0.5, "managerCost": 0.1} if inp["companyId"] == "k1" else None)
                elif proc == "employee.getCompanyEmployees":
                    res.append([{"wage": 0.2}, {"wage": 0.3}] if inp["companyId"] == "k1" else [{"wage": 0.05}])
            out.append(res)
        return out


class StaffTests(unittest.TestCase):
    def test_workers_and_wage_fallback(self):
        import os
        os.environ["WARTRACK_HOST"] = "all"
        try:
            db = dbm.connect(":memory:")
            EC.collect_companies(Fake(), db, Scope())
        finally:
            del os.environ["WARTRACK_HOST"]
        rows = {r["id"]: (r["workers"], r["wages"], r["mgr"]) for r in db.execute("SELECT id, workers, wages, mgr FROM companies")}
        self.assertEqual(rows["k1"], (2, 0.5, 0.1))      # wages from the estimate, 2 employees listed
        self.assertEqual(rows["k2"], (1, 0.05, 0.0))     # no estimate: the listed employees' wages


if __name__ == "__main__":
    unittest.main()
