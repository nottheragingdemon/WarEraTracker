"""The weekly digest text, built from a small in-memory database."""
import datetime as dt, sqlite3, unittest

from wartrack import alerts, db as dbm


class FakeScope:
    members = ["c1", "c2"]
    since = None

    def battle_sql(self, alias="b"):
        return f"({alias}.att_country IN ('c1','c2') OR {alias}.def_country IN ('c1','c2'))", []


class DigestTests(unittest.TestCase):
    def test_digest_text(self):
        db = dbm.connect(":memory:")
        now = dt.datetime(2026, 11, 26, 8, tzinfo=dt.timezone.utc)
        db.execute("INSERT INTO battles(id,created_at,att_country,def_country,is_active) VALUES('b1','2026-11-25T10:00:00Z','c1','x',0)")
        db.execute("INSERT INTO battles(id,created_at,att_country,def_country,is_active) VALUES('old','2026-11-01T10:00:00Z','c1','x',0)")
        for bid, kind, v in (("b1", "damage", 5e6), ("b1", "money", 500.0), ("old", "damage", 9e9)):
            db.execute("INSERT INTO battle_stat VALUES(?,?,?,?,?,?)", (bid, kind, "country", "c1", "a", v))
            db.execute("INSERT INTO battle_stat VALUES(?,?,?,?,?,?)", (bid, kind, "user", "u1", "a", v))
        db.execute("INSERT INTO users(id,country,name) VALUES('u1','c1','Ann')")
        db.execute("INSERT INTO names VALUES('country','c1','Alpha',NULL)")
        db.execute("INSERT INTO names VALUES('user','u1','Ann',NULL)")
        db.execute("INSERT INTO transfers VALUES('t1','2026-11-25T12:00:00Z','c1','c2',1500)")
        db.execute("INSERT INTO donations VALUES('d1','2026-11-25T12:00:00Z','c1','u1',250,'c1')")
        text = alerts.digest_text(db, FakeScope(), now=now)
        self.assertIn("**1** battles involving the alliance", text)     # the old battle is outside the week
        self.assertIn("🥇 Alpha — **5.00M**", text)                             # country damage, old battle excluded
        self.assertIn("🥇 Ann — **100.0**", text)                                 # 500 money / 5M damage = 100 per 1M
        self.assertIn("**1** transfers · **1.50k** in total", text)
        self.assertIn("**250** from **1** citizens", text)
        self.assertLess(len(text), 1900)


if __name__ == "__main__":
    unittest.main()
