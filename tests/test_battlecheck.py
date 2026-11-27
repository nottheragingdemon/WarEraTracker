import datetime as dt, importlib.util, os, unittest

spec = importlib.util.spec_from_file_location("battlecheck", os.path.join(os.path.dirname(__file__), "..", "scripts", "battlecheck.py"))
bc = importlib.util.module_from_spec(spec); spec.loader.exec_module(bc)


class StaleCheck(unittest.TestCase):
    now = dt.datetime(2026, 11, 27, 15, 0, tzinfo=dt.timezone.utc)

    def gen(self, hours):
        return {"generated": (self.now - dt.timedelta(hours=hours)).isoformat()}

    def test_fresh_is_silent(self):
        st = {}
        self.assertIsNone(bc.stale_check(self.gen(1), st, self.now)); self.assertEqual(st, {})

    def test_alerts_once_then_recovers(self):
        st = {}
        self.assertIn("hours old", bc.stale_check(self.gen(5), st, self.now))
        self.assertIsNone(bc.stale_check(self.gen(6), st, self.now))
        self.assertIn("updating again", bc.stale_check(self.gen(0.5), st, self.now))
        self.assertNotIn("stale_alert", st)

    def test_bad_timestamp_ignored(self):
        self.assertIsNone(bc.stale_check({"generated": "x"}, {}, self.now))
        self.assertIsNone(bc.stale_check({}, {}, self.now))


class EmptyParts(unittest.TestCase):
    def test_reports_missing_and_empty(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as d:
            json.dump({"nonEmpty": ["ents"], "parts": {"b.json": ["statsP"]}}, open(os.path.join(d, "contract.json"), "w"))
            json.dump({"ents": []}, open(os.path.join(d, "data.json"), "w"))
            self.assertEqual(bc.empty_parts(d), ["ents", "b.json"])
            json.dump({"statsP": []}, open(os.path.join(d, "b.json"), "w"))
            self.assertEqual(bc.empty_parts(d), ["ents", "b.json:statsP"])
            json.dump({"ents": [1]}, open(os.path.join(d, "data.json"), "w")); json.dump({"statsP": [1]}, open(os.path.join(d, "b.json"), "w"))
            self.assertEqual(bc.empty_parts(d), [])
