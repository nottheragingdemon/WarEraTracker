"""Player efficiency stage: daily snapshots, skill points and builds, with a fake API client."""
import unittest

from wartrack import collect as C, db as dbm


class Scope:
    members = ["c1"]


class FakeClient:
    def __init__(self):
        self.n = 0
        self.skill_calls = 0

    def pages(self, proc, **kw):
        assert proc == "ranking.getRankingPage" and kw["rankingType"] == "weeklyUserDamages"
        yield from [{"user": "war", "value": 3e6}, {"user": "eco", "value": 1.5e6}, {"user": "low", "value": 1000}]

    def map(self, fn, items, workers=None):
        return [fn(x) for x in items]

    def lookup_users(self, ids):
        out = {}
        for u in ids:
            out[u] = {"username": u.upper(), "country": "c1" if u != "away" else "c9", "mu": "m1",
                      "rankings": {"userWealth": {"value": 1000.0}, "userDamages": {"value": 5e7}, "weeklyUserDamages": {"value": 3e6}},
                      "dates": {"lastSkillsResetAt": "2026-11-20T00:00:00Z"}}
        return out

    def batch_many(self, lists, official=False):
        self.skill_calls += sum(len(l) for l in lists)
        lv = {"war": {"attack": 10, "precision": 10, "companies": 2}, "eco": {"companies": 10, "management": 10, "energy": 4}}
        return [[{"skills": {k: {"level": v} for k, v in lv[c[1]["userId"]].items()},
                  "leveling": {"spentSkillPoints": sum(x * (x + 1) // 2 for x in lv[c[1]["userId"]].values())},
                  "dates": {"lastSkillsResetAt": "2026-11-20T00:00:00Z"}} for c in l] for l in lists]


class EfficiencyTests(unittest.TestCase):
    def test_skill_points(self):
        self.assertEqual([C.skill_points(x) for x in (0, 1, 4, 10)], [0, 1, 10, 55])

    def test_stage(self):
        db, c = dbm.connect(":memory:"), FakeClient()
        C.collect_efficiency(c, db, Scope())
        self.assertEqual(sorted(r[0] for r in db.execute("SELECT eid FROM player_now")), ["eco", "war"])   # below the weekly floor: skipped
        sk = {r["eid"]: (r["spent"], r["eco"]) for r in db.execute("SELECT * FROM player_skill")}
        self.assertEqual(sk["war"], (113, 3))     # 55 + 55 + 3, of which companies 3
        self.assertEqual(sk["eco"], (120, 120))   # 55 + 55 + 10, all economy
        self.assertEqual(db.execute("SELECT COUNT(*) FROM player_snap").fetchone()[0], 2)
        C.collect_efficiency(c, db, Scope())      # same day: snapshot replaced, skills not fetched again
        self.assertEqual(db.execute("SELECT COUNT(*) FROM player_snap").fetchone()[0], 2)
        self.assertEqual(c.skill_calls, 2)


if __name__ == "__main__":
    unittest.main()
