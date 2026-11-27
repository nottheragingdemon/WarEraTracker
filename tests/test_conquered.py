"""Conquered regions: wage snapshots split by the region's core (original) country, and the export carries it."""
import time, unittest

from wartrack import db as dbm, export as X
from wartrack.stages.economy import snapshot_wages


class ConqueredTests(unittest.TestCase):
    def test_snapshots_split_by_core_and_export(self):
        d = dbm.connect(":memory:")
        # r1 is the host's own region; r2 was conquered from c9
        d.execute("INSERT INTO region_now(region,name,country,core) VALUES('r1','R1','c1','c1'),('r2','R2','c1','c9')")
        rows = [("a", "A", "o", "x", 0, "r1", "c2", None, 3, 10.0, 1.0),
                ("b", "B", "o", "x", 0, "r2", "c2", None, 2, 4.0, 0.5),
                ("c", "C", "o", "x", 0, "r2", "c9", None, 1, 2.0, 0.0)]
        snapshot_wages(d, rows)
        got = {(r["host"], r["core"], r["owner_country"]): (r["companies"], r["workers"], r["wages"])
               for r in d.execute("SELECT * FROM wage_snap3")}
        self.assertEqual(got, {("c1", "c1", "c2"): (1, 3, 10.0), ("c1", "c9", "c2"): (1, 2, 4.0), ("c1", "c9", "c9"): (1, 1, 2.0)})
        # an old host-level row from before the split has no core field in the export
        d.executescript(dbm.LEGACY_WAGE_SCHEMA)
        d.execute("INSERT INTO wage_snap2 VALUES('c1','c2',?,2,5,14.0,0)", (int(time.time() * 1000) - 3600000,))
        ents, idx = [], {}
        def E(t, i):
            if (t, i) not in idx:
                idx[(t, i)] = len(ents); ents.append([t, i, None])
            return idx[(t, i)]
        out = X.company_history(d, E)
        self.assertEqual(sorted(len(r) for r in out), [7, 8, 8, 8])
        self.assertIn(E("country", "c9"), [r[7] for r in out if len(r) == 8])


if __name__ == "__main__":
    unittest.main()


class PackAndFullTests(unittest.TestCase):
    def test_pack_companies_round_trip(self):
        cx = {"companies": [["A", 1, "bread", 5, "regionid000000000000001", 2, 3, 1.5, 0.0], ["B", 1, "wood", 5, "regionid000000000000001", 2, 0, 0.0, 0.0]],
              "wageHistReg": [["regionid000000000000001", 2, 1, 1, 3, 1.5, 0.0]], "wageHist": []}
        p = X.pack_companies(cx)
        self.assertEqual(p["regionKeys"], ["regionid000000000000001"])
        self.assertEqual(p["items"], ["bread", "wood"])
        self.assertEqual([c[2] for c in p["companies"]], [0, 1])
        self.assertEqual(p["companies"][0][4], 0)
        self.assertEqual(p["wageHistReg"][0][0], 0)

    def test_coverage_counts_full_storage(self):
        from wartrack.stages.economy import coverage_rows
        d = dbm.connect(":memory:")
        d.execute("INSERT INTO region_now(region,name,country,emp,mgr,companies,employees,core) VALUES('r1','R1','h',1.0,0,2,5,'h')")
        d.execute("INSERT INTO country_tax(country,name,income,manager) VALUES('h','H',10,0)")
        d.execute("INSERT INTO companies(id,region,workers,wages,mgr,full) VALUES('a','r1',3,6.0,0,0),('b','r1',2,4.0,0,1)")
        r = coverage_rows(d, {"h"})[0]
        self.assertEqual((r[2], r[4], r[8], r[9]), (2, 1.0, 1, 0.6))   # 2 staffed, tax 10% of 10; 1 full; 10% of 6 without it


class ThinTests(unittest.TestCase):
    def test_tiers(self):
        H, D = 3_600_000, 86_400_000
        now = 100 * D
        evs = [(now - h * H, [h]) for h in range(0, 60 * 24, 1)]   # hourly for 60 days
        out = X._thin(evs, now - 48 * H, 6 * H, now - 35 * D)
        recent = [t for t, _ in out if t >= now - 48 * H]
        mid = [t for t, _ in out if now - 35 * D <= t < now - 48 * H]
        old = [t for t, _ in out if t < now - 35 * D]
        self.assertEqual(len(recent), 48)
        self.assertLessEqual(len(mid), 33 * 4 + 2)
        self.assertLessEqual(len(old), 26)
        self.assertEqual([t for t, _ in out], sorted(t for t, _ in out))
