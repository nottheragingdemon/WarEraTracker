import importlib.util, os, urllib.error, unittest

spec = importlib.util.spec_from_file_location("live_check", os.path.join(os.path.dirname(__file__), "..", "scripts", "live_check.py"))
lc = importlib.util.module_from_spec(spec); spec.loader.exec_module(lc)


class LiveCheck(unittest.TestCase):
    def test_up_asleep_and_down(self):
        up = lambda u: (200, "ok") if u.endswith("_stcore/health") else (200, "<html>app</html>")
        self.assertEqual(lc.check(up, "https://x/"), (True, "the app is up"))
        asleep = lambda u: (200, "Yes, get this app back up!")
        self.assertTrue(lc.check(asleep, "https://x/")[0])

        def err(u):
            raise urllib.error.HTTPError(u, 503, "x", {}, None)
        self.assertFalse(lc.check(err, "https://x/")[0])
        bad = lambda u: (200, "nope") if u.endswith("_stcore/health") else (200, "<html></html>")
        self.assertFalse(lc.check(bad, "https://x/")[0])
