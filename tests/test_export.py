"""The exported data.json / ask-data.json: shape, packed per-battle stats, splits and day aggregates."""
import datetime as dt, json, os, tempfile, unittest

from wartrack import db as dbm, export as X


class Scope:
    members = ["c1"]
    alliance_id = None
    active = True
    since = "2026-11-01T00:00:00Z"

    def battle_sql(self, alias="b"):
        return f"({alias}.att_country='c1' OR {alias}.def_country='c1')", []


def unpack(sp):
    return sorted([k, b, x // 3, x % 3, f[i + 1]] for k, b, f in sp for i, x in enumerate(f) if i % 2 == 0)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.db = dbm.connect(":memory:")
        d = self.db
        now = dt.datetime.now(dt.timezone.utc)
        d.execute("INSERT INTO battles(id,created_at,is_active,att_country,def_country,att_damage,def_damage) VALUES('b1','2026-11-20T10:00:00Z',0,'c1','c2',100,200)")
        for kind, et, eid, side, v in (("damage", "country", "c1", "a", 1500.0), ("money", "country", "c1", "a", 12.5),
                                       ("damage", "user", "u1", "a", 700.0), ("damage", "country", "c2", "d", 2000.0)):
            d.execute("INSERT INTO battle_stat VALUES('b1',?,?,?,?,?)", (kind, et, eid, side, v))
        d.execute("INSERT INTO bounty_snap VALUES('2026-11-26T00:00:00Z','userBounty','u1',5,'c1',NULL)")
        d.execute("INSERT INTO country_tax VALUES('c1','Alpha',17,0,1.5)")
        t = int(now.timestamp() * 1000)
        d.execute("INSERT INTO country_income VALUES('c1',?,100,?)", (t - t % 3600000, json.dumps({"total": 10, "development": 2})))
        d.execute("INSERT INTO country_income VALUES('c1',?,90,?)", (t - t % 3600000 - 3600000, json.dumps({"total": 20, "development": 4})))
        d.execute("INSERT INTO trades VALUES('t1',?,'c1','zz',300,'fish',3)", (now.isoformat(timespec="seconds").replace("+00:00", "Z"),))
        d.commit()
        self.dir = tempfile.mkdtemp()
        X.export(d, os.path.join(self.dir, "data.json"), "2026-11-01T00:00:00Z", Scope())
        with open(os.path.join(self.dir, "data.json")) as f:
            self.data = json.load(f)
        with open(os.path.join(self.dir, "ask-data.json")) as f:
            self.ask = json.load(f)
        with open(os.path.join(self.dir, "company-data.json")) as f:
            self.company = json.load(f)

    def test_shape(self):
        for k in ("v", "generated", "ents", "battles", "statsP", "players", "playerHist", "status", "countryIncomeDays", "tradeDays", "marketRate"):
            self.assertIn(k, self.data)
        self.assertEqual(self.data["v"], 3)
        self.assertNotIn("stats", self.data)
        self.assertNotIn("bounty", self.data)               # moved to ask-data.json
        self.assertEqual(len(self.ask["bounty"]), 1)
        self.assertEqual(self.ask["generated"], self.data["generated"])
        self.assertNotIn("wageHist", self.data)             # moved to company-data.json
        self.assertIn("wageHist", self.company)
        self.assertNotIn("companies", self.data)
        self.assertIn("companies", self.company)

    def test_packed_stats_round_trip(self):
        E = self.data["ents"]
        rows = unpack(self.data["statsP"])
        self.assertEqual(len(rows), 4)
        named = {(r[0], E[r[2]][1], r[3]): r[4] for r in rows}
        self.assertEqual(named[(0, "c1", 0)], 1500)          # integral values exported as ints
        self.assertEqual(named[(1, "c1", 0)], 12.5)
        self.assertEqual(named[(0, "c2", 1)], 2000)

    def test_company_history_levels_and_thinning(self):
        import time
        now = int(time.time() * 1000)
        d = self.db
        d.execute("INSERT INTO region_now(region,name,country) VALUES('r1','R1','c1'),('r2','R2','c1')")
        d.executescript(dbm.LEGACY_WAGE_SCHEMA)
        # old per-region rows two days ago (summed per host), new host-level rows: hourly in the last 48 h kept, older thinned
        d.execute("INSERT INTO wage_snap VALUES('r1','c2',?,1,2,1.0,0)", (now - 80 * 3600000,))
        d.execute("INSERT INTO wage_snap VALUES('r2','c2',?,1,3,2.0,0)", (now - 80 * 3600000 + 1000,))
        for h in range(72, 0, -1):
            d.execute("INSERT INTO wage_snap2 VALUES('c1','c2',?,2,5,?,0)", (now - h * 3600000, 3.0 + h / 1000))
        ents, idx = [], {}
        def E(t, i):
            if (t, i) not in idx:
                idx[(t, i)] = len(ents); ents.append([t, i, None])
            return idx[(t, i)]
        rows = X.company_history(d, E)
        self.assertTrue(all(r[0] == E("country", "c1") and r[1] == E("country", "c2") for r in rows))
        old = [r for r in rows if r[2] < now - 79 * 3600000]
        self.assertEqual([r[5] for r in old][-1], 3.0)      # the two regions summed: 1.0 + 2.0
        recent = [r for r in rows if r[2] >= now - 48 * 3600000]
        self.assertEqual(len(recent), 48)                   # every snapshot of the last 48 h
        self.assertLess(len(rows) - len(recent), 10)        # older ones: one per 6-hour block

    def test_day_aggregates(self):
        inc = self.data["countryIncomeDays"]
        self.assertTrue(inc)
        # one row per country and day: the day's average hourly rate x 24 (two samples of 10 and 20 an hour; a run just after
        # midnight puts them on different days)
        expected = [240.0] if len(inc) == 1 and inc[0][2] == 1 else [360.0] if len(inc) == 1 else [480.0, 240.0]
        self.assertEqual([r[4]["total"] for r in inc], expected)
        self.assertEqual(inc[-1][3], 100)                    # treasury at the latest check of the day
        td = self.data["tradeDays"]
        self.assertEqual(td[0][2:], [300, 1])
        E = self.data["ents"]
        self.assertEqual(self.data["marketRate"][str([i for i, e in enumerate(E) if e[1] == "c1"][0])], 1.5)


if __name__ == "__main__":
    unittest.main()
