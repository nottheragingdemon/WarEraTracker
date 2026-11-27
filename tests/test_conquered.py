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
