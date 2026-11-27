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

    def test_redirect_on_first_visit_is_fine(self):
        def f(u):
            if u.endswith("_stcore/health"):
                return 200, "ok"
            raise urllib.error.HTTPError(u, 303, "see other", {}, None)
        self.assertTrue(lc.check(f, "https://x/")[0])

    def test_redirect_loop_everywhere_is_up_but_5xx_is_not(self):
        def loop(u):
            raise urllib.error.HTTPError(u, 303, "x", {}, None)
        self.assertTrue(lc.check(loop, "https://x/")[0])

        def down(u):
            if u.endswith("_stcore/health"):
                raise urllib.error.HTTPError(u, 503, "x", {}, None)
            return 200, "<html></html>"
        self.assertFalse(lc.check(down, "https://x/")[0])
