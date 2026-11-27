"""Market trades for the market tax estimate: incremental with a one-off backfill."""
import datetime as dt, unittest

from wartrack import collect as C, db as dbm


def iso(d):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=d)).isoformat(timespec="seconds").replace("+00:00", "Z")


class Scope:
    members = ["c1"]


class Fake:
    def __init__(self, items):
        self.items, self.read = items, 0

    def pages(self, proc, **kw):
        assert kw["transactionType"] == "trading"
        for t in self.items:
            self.read += 1
            yield t

    def map(self, fn, xs, workers=None):
        return [fn(x) for x in xs]


class TradeTests(unittest.TestCase):
    def test_trades(self):
        items = [{"_id": f"t{d}", "createdAt": iso(d + 0.5), "buyerCountryId": "zz", "money": 100.0, "itemCode": "paper", "quantity": 5} for d in range(40)]
        db = dbm.connect(":memory:")
        C.collect_trades(Fake(items), db, Scope(), days=30)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 30)
        f = Fake([{"_id": "new", "createdAt": iso(0), "buyerCountryId": "c1", "money": 50, "itemCode": "fish", "quantity": 1}] + items)
        C.collect_trades(f, db, Scope(), days=30)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM trades").fetchone()[0], 31)
        self.assertEqual(f.read, 2)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM trades WHERE country='c1' AND buyer_country='zz'").fetchone()[0], 30)   # listed under c1, bought from zz


if __name__ == "__main__":
    unittest.main()
