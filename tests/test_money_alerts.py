"""Money alerts: large transfers, big donation days, treasury drops; baselines first so old events are never posted."""
import datetime as dt, unittest

from wartrack import alerts, db as dbm

NOW = dt.datetime(2026, 11, 27, 12, tzinfo=dt.timezone.utc)
MS = lambda h: int((NOW - dt.timedelta(hours=h)).timestamp() * 1000)


class MoneyAlertTests(unittest.TestCase):
    def setUp(self):
        self.db = dbm.connect(":memory:")
        self.db.execute("CREATE TABLE IF NOT EXISTS alert_state(k TEXT PRIMARY KEY, v TEXT)")
        for c, n in (("c1", "Alpha"), ("c2", "Beta")):
            self.db.execute("INSERT INTO names VALUES('country',?,?,NULL)", (c, n))
        self.db.execute("INSERT INTO names VALUES('user','u1','Big_Giver',NULL)")

    def run_alerts(self):
        return alerts.money_lines(self.db, ["c1", "c2"], now=NOW)

    def test_transfers(self):
        self.db.execute("INSERT INTO transfers VALUES('old','2026-11-20T00:00:00Z','c1','c2',9000)")
        self.assertEqual(self.run_alerts(), [])                                   # baseline only
        self.db.execute("INSERT INTO transfers VALUES('t1','2026-11-27T10:00:00Z','c1','c2',6000)")
        self.db.execute("INSERT INTO transfers VALUES('t2','2026-11-27T10:05:00Z','c2','c1',100)")
        out = self.run_alerts()
        self.assertEqual(len(out), 1)
        self.assertIn("Alpha → Beta **6.00k**", out[0])
        self.assertEqual(self.run_alerts(), [])                                   # not repeated

    def test_donation_days(self):
        for i in range(30):
            self.db.execute("INSERT INTO donations VALUES(?,?,?,?,?,?)", (f"d{i}", "2026-11-27T09:00:00Z", "c1", "u1", 200, "c1"))
        self.assertEqual(self.run_alerts(), [])                                   # first run: baseline
        for i in range(30, 60):
            self.db.execute("INSERT INTO donations VALUES(?,?,?,?,?,?)", (f"d{i}", "2026-11-26T09:00:00Z", "c1", "u1", 200, "c1"))
        out = self.run_alerts()
        self.assertEqual(len(out), 1)
        self.assertIn("Big\\_Giver gave Alpha **6.00k** in 30 donations on 2026-11-26", out[0])
        self.assertEqual(self.run_alerts(), [])

    def test_treasury_drop(self):
        for h, m in ((20, 9000), (10, 8000), (1, 1000)):
            self.db.execute("INSERT INTO country_income VALUES(?,?,?,?)", ("c1", MS(h), m, "{}"))
        out = self.run_alerts()
        self.assertEqual(len(out), 1)
        self.assertIn("Alpha fell from **9.00k** to **1.00k**", out[0])
        self.assertEqual(self.run_alerts(), [])                                   # quiet for 12 hours


if __name__ == "__main__":
    unittest.main()
