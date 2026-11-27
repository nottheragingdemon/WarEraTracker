import importlib.util, os, unittest

spec = importlib.util.spec_from_file_location("live_pages", os.path.join(os.path.dirname(__file__), "..", "scripts", "live_pages.py"))
L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)


class Judge(unittest.TestCase):
    def test_states(self):
        self.assertEqual(L.judge("Updated 2026-11-27 17:46 UTC · 62 battles", "Updated")[0], "ok")
        self.assertEqual(L.judge("Could not load data.json: x", "Updated")[0], "bad")
        self.assertEqual(L.judge("Loading…", "Updated")[0], "bad")
        self.assertEqual(L.judge("", "Updated")[0], "unknown")
        self.assertEqual(L.judge("Sign in to continue", "Updated")[0], "unknown")


if __name__ == "__main__":
    unittest.main()
