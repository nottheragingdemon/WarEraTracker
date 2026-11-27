"""Pruning keeps the window and thins old bounty snapshots."""
import datetime as dt, unittest

from wartrack import collect as C, db as dbm


def iso(days_ago, hour=12):
    d = dt.datetime.now(dt.timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0) - dt.timedelta(days=days_ago)
    return d.isoformat(timespec="seconds").replace("+00:00", "Z")


class PruneTests(unittest.TestCase):
    def test_prune(self):
        db = dbm.connect(":memory:")
        db.execute("INSERT INTO battles(id,created_at,is_active) VALUES('old',?,0)", (iso(100),))
        db.execute("INSERT INTO battles(id,created_at,is_active) VALUES('new',?,0)", (iso(5),))
        db.execute("INSERT INTO battles(id,created_at,is_active) VALUES('live',?,1)", (iso(100),))
        for b in ("old", "new", "live"):
            db.execute("INSERT INTO battle_stat VALUES(?,?,?,?,?,?)", (b, "damage", "country", "c", "a", 1))
        for d, h in ((20, 6), (20, 18), (3, 6), (3, 18), (95, 12)):
            db.execute("INSERT INTO bounty_snap VALUES(?,?,?,?,?,?)", (iso(d, h), "userBounty", "u", 1, None, None))
        db.executescript(dbm.LEGACY_WAGE_SCHEMA)
        db.execute("INSERT INTO wage_snap VALUES('r','c',?,1,1,1.0,0)", (int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=95)).timestamp() * 1000),))
        db.execute("INSERT INTO wage_snap2 VALUES('h','c',?,1,1,1.0,0)", (int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).timestamp() * 1000),))
        C.prune(db, 90)
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("wage_snap", tables)    # retired format, nothing left inside the 92-day history: dropped
        self.assertIn("wage_snap2", tables)      # still has recent rows
        self.assertEqual(sorted(r[0] for r in db.execute("SELECT id FROM battles")), ["live", "new"])   # active battles are kept
        self.assertEqual(db.execute("SELECT COUNT(*) FROM battle_stat").fetchone()[0], 2)
        snaps = [r[0] for r in db.execute("SELECT ts FROM bounty_snap ORDER BY ts")]
        self.assertEqual(snaps, [iso(20, 18), iso(3, 6), iso(3, 18)])   # 95 days: gone; 20 days: last of the day; 3 days: all


if __name__ == "__main__":
    unittest.main()
