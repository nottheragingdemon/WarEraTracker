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
        self.assertIn("⚔️ Battles: **1** (new)", text)     # the old battle is outside the week
        self.assertIn("🥇 Alpha — **5.00M**", text)                             # country damage, old battle excluded
        self.assertIn("🥇 Ann — **100.0**", text)                                 # 500 money / 5M damage = 100 per 1M
        self.assertIn("Transfers between nations: **1.50k**", text)
        self.assertIn("Citizen donations: **250**", text)
        self.assertIn("**1** citizens donated", text)
        self.assertLess(len(text), 1900)


class EndedTests(unittest.TestCase):
    def test_ended_line(self):
        db = dbm.connect(":memory:")
        db.execute("INSERT INTO names VALUES('country','c1','Alpha',NULL)")
        db.execute("INSERT INTO names VALUES('country','x','Xland',NULL)")
        db.execute("""INSERT INTO battles(id,created_at,ended_at,is_active,att_country,def_country,won_by,att_damage,def_damage)
                      VALUES('b9','2026-11-25T10:00:00Z','2026-11-25T20:00:00Z',0,'x','c1','defender',2e6,3e6)""")
        b = db.execute("SELECT * FROM battles").fetchone()
        line = alerts._ended_line(db, b, {"c1"})
        self.assertTrue(line.startswith("✅ Battle won: Xland vs Alpha"))
        self.assertIn("Alpha won · damage 2.00M vs 3.00M", line)
        self.assertTrue(line.endswith("/battle/b9"))
        self.assertTrue(alerts._ended_line(db, b, {"x"}).startswith("❌ Battle lost"))


if __name__ == "__main__":
    unittest.main()
