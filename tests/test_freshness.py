"""Freshness checks: stale data is flagged and alerted once (then every 6 hours), with a note when it recovers."""
import datetime as dt, unittest

from wartrack import alerts, db as dbm
from wartrack.stages import health

NOW = dt.datetime(2026, 11, 27, 12, tzinfo=dt.timezone.utc)
iso = lambda h: (NOW - dt.timedelta(hours=h)).isoformat(timespec="seconds").replace("+00:00", "Z")
ms = lambda h: int((NOW - dt.timedelta(hours=h)).timestamp() * 1000)


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.db = dbm.connect(":memory:")
        self.db.execute("CREATE TABLE IF NOT EXISTS alert_state(k TEXT PRIMARY KEY, v TEXT)")

    def states(self):
        return {f["key"]: f["state"] for f in health.freshness(self.db, NOW)}

    def test_states(self):
        self.db.execute("INSERT INTO country_income VALUES('c1',?,1,'{}')", (ms(0.5),))
        self.db.execute("INSERT INTO run_stats VALUES(?,'full',60,100,0,'','[]')", (iso(5),))
        self.db.execute("INSERT INTO coverage_hist VALUES(?,'c1',1,1,1,1,1,1)", ((NOW - dt.timedelta(days=1)).date().isoformat(),))
        st = self.states()
        self.assertEqual(st["income"], "ok")
        self.assertEqual(st["refresh"], "stale")     # 5 h > 2.5 h
        self.assertEqual(st["coverage"], "ok")       # yesterday's day counts until its end + 26 h
        self.assertEqual(st["companies"], "none")    # no data yet: not an alarm

    def test_alert_once_then_recovery(self):
        self.db.execute("INSERT INTO country_income VALUES('c1',?,1,'{}')", (ms(4),))
        out = alerts.stale_lines(self.db, NOW)
        self.assertEqual(len(out), 1)
        self.assertIn("Country income history recorded, last 4.0 h ago", out[0])
        self.assertEqual(alerts.stale_lines(self.db, NOW + dt.timedelta(hours=1)), [])        # quiet for 6 hours
        self.db.execute("INSERT INTO country_income VALUES('c1',?,1,'{}')", (ms(0),))
        self.assertEqual(alerts.stale_lines(self.db, NOW), ["✅ Data flowing again: Country income history recorded"])


if __name__ == "__main__":
    unittest.main()
