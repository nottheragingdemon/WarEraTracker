"""Donations: newest first, stop at the first stored one, plus a one-off backfill to the full window."""
import datetime as dt, unittest

from wartrack import collect as C, db as dbm


def iso(days_ago):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)).isoformat(timespec="seconds").replace("+00:00", "Z")


class Scope:
    members = ["c1"]


class Fake:
    def __init__(self, items):
        self.items, self.read = items, 0

    def pages(self, proc, **kw):
        for t in self.items:
            self.read += 1
            yield t

    def map(self, fn, xs, workers=None):
        return [fn(x) for x in xs]

    def lookup_users(self, ids):
        return {u: {"country": "c1"} for u in ids}


class DonationTests(unittest.TestCase):
    def test_backfill_then_incremental(self):
        items = [{"_id": f"t{d}", "createdAt": iso(d), "sellerCountryId": "c1", "buyerId": "u", "money": 1} for d in range(1, 100, 5)]
        db = dbm.connect(":memory:")
        for t in items[:13]:   # already stored: the newest 60 days
            db.execute("INSERT INTO donations VALUES(?,?,?,?,?,?)", (t["_id"], t["createdAt"], "c1", "u", 1, "c1"))
        f = Fake(items)
        C.collect_donations(f, db, Scope(), days=90)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM donations").fetchone()[0], 18)   # 1..86 days: backfilled past the stored ones
        f2 = Fake([{"_id": "new", "createdAt": iso(0), "sellerCountryId": "c1", "buyerId": "u", "money": 1}] + items)
        C.collect_donations(f2, db, Scope(), days=90)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM donations").fetchone()[0], 19)
        self.assertEqual(f2.read, 2)   # backfill done: stops at the first stored donation


if __name__ == "__main__":
    unittest.main()
