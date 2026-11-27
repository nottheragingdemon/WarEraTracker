"""Month statements: worked out like the Company page, frozen once on the 1st, and posted as text."""
import datetime as dt, unittest

from wartrack import db as dbm, statement as S


def ms(s):
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


class StatementTests(unittest.TestCase):
    def setUp(self):
        from wartrack.stages import common
        self._ag, common.AGREEMENTS_FILE = common.AGREEMENTS_FILE, "/nonexistent/agreements.json"
        d = self.db = dbm.connect(":memory:")
        d.execute("INSERT INTO country_tax(country,name,income,manager) VALUES('h','Hland',10,0),('o','Oland',5,0),('c','Cland',5,0)")
        d.execute("INSERT INTO region_now(region,name,country,core) VALUES('r1','R1','h','h'),('r2','R2','h','c')")
        d.execute("INSERT INTO rate_hist VALUES('h',?,10,0)", (ms("2026-10-01T00:00:00"),))
        # two checks 2 hours apart on 31 Oct 23:00 and 1 Nov 01:00, then one more at 03:00
        for t in ("2026-10-31T23:00:00", "2026-11-01T01:00:00", "2026-11-01T03:00:00"):
            d.execute("INSERT INTO run_log VALUES(?)", (ms(t),))
        t0 = ms("2026-10-31T22:00:00")
        d.execute("INSERT INTO wage_snap3 VALUES('h','h','o',?,1,3,100.0,0)", (t0,))   # own region: 10 tax/h
        d.execute("INSERT INTO wage_snap3 VALUES('h','c','o',?,1,2,50.0,0)", (t0,))    # conquered from c: 5 tax/h, 10% to c

    def tearDown(self):
        from wartrack.stages import common
        common.AGREEMENTS_FILE = self._ag

    def test_agreements_filter(self):
        import json, os, tempfile
        from wartrack.stages import common
        self.db.execute("INSERT INTO wage_snap3 VALUES('h','h','c',?,1,1,20.0,0)", (ms("2026-10-31T22:00:00"),))
        path = os.path.join(tempfile.mkdtemp(), "agreements.json")
        json.dump({"agreements": {"Hland": ["Cland"]}}, open(path, "w"))
        common.AGREEMENTS_FILE = path
        rows = S.compute(self.db, "h", "2026-11", now_ms=ms("2026-11-01T05:00:00"))
        self.assertEqual(set(rows), {"c"})   # Oland has no agreement with Hland: left out

    def test_compute_month_split(self):
        # November: from 00:00 to the last check's 6-hour cap (03:00 + up to 6 h, cut at 'now')
        rows = S.compute(self.db, "h", "2026-11", now_ms=ms("2026-11-01T05:00:00"))
        # 23:00 check covers 00:00-01:00 (1 h), 01:00 check 2 h, 03:00 check to 05:00 2 h: 5 h x 15 = 75; to core 5 h x 0.5
        self.assertAlmostEqual(rows["o"][0], 75.0, places=3)
        self.assertAlmostEqual(rows["o"][1], 2.5, places=3)
        rows = S.compute(self.db, "h", "2026-10", now_ms=ms("2026-11-01T05:00:00"))
        self.assertAlmostEqual(rows["o"][0], 15.0, places=3)   # 23:00-24:00 in October

    def test_freeze_once_and_text(self):
        now = dt.datetime(2026, 12, 1, 2, tzinfo=dt.timezone.utc)
        self.assertEqual(S.freeze(self.db, {"h"}, now, log=lambda *_: None), "2026-11")
        n = self.db.execute("SELECT COUNT(*) FROM statements").fetchone()[0]
        S.freeze(self.db, {"h"}, now, log=lambda *_: None)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM statements").fetchone()[0], n)   # not again
        txt = S.text(self.db, "2026-11", "h")
        self.assertIn("Hland: company tax statement, November 2026", txt)
        self.assertIn("Oland", txt)
        self.assertIn("to core", txt)


if __name__ == "__main__":
    unittest.main()
