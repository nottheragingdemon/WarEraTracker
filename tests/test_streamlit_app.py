"""The Streamlit app starts and renders its menu without errors (skipped when Streamlit isn't installed)."""
import os, unittest

try:
    from streamlit.testing.v1 import AppTest
except Exception:   # noqa: BLE001
    AppTest = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@unittest.skipUnless(AppTest, "needs streamlit")
class StreamlitAppTests(unittest.TestCase):
    def test_app_runs_with_menu(self):
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            at = AppTest.from_file(os.path.join(ROOT, "streamlit_app.py"), default_timeout=60).run()
        finally:
            os.chdir(cwd)
        self.assertFalse(at.exception, [e.message for e in at.exception])
        labels = [p.label for p in at.get("page_link")]
        for want in ("Tracker", "Taxes", "Transfers", "Efficiency", "Status", "Guide", "MapTap", "Boreen"):
            self.assertIn(want, labels)
        self.assertNotIn("Ask", labels)   # hidden without the dev key
        self.assertNotIn("Settings", labels)

    def test_settings_page_with_dev_key(self):
        at = AppTest.from_file(os.path.join(ROOT, "streamlit_app.py"), default_timeout=60)
        at.secrets["DEV_KEY"] = "k"
        at.query_params["key"] = "k"
        at.run()
        self.assertIn("Settings", [p.label for p in at.get("page_link")])


if __name__ == "__main__":
    unittest.main()


class PreviewChanges(unittest.TestCase):
    def test_rate_change_estimate_and_add_remove(self):
        import importlib.util, os
        spec = importlib.util.spec_from_file_location("sa", os.path.join(os.path.dirname(__file__), "..", "streamlit_app.py"))
        # streamlit_app runs page code on import, so exercise the function by source instead
        src = open(spec.origin).read()
        ns = {}
        start = src.index("def preview_changes"); end = src.index("def settings")
        exec(src[start:end], ns)
        data = {"ents": [["country", "a", "Ireland"], ["country", "b", "Mexico"], ["country", "c", "Chile"]],
                "statementsLive": {"2026-11": {"0": [[1, 1000.0, 0, 1000.0]]}}}
        cur = {"Ireland": [{"country": "Mexico", "regions": "core", "pay_percent": 100, "payments_since": "2026-11-01"}]}
        new = {"Ireland": [{"country": "Mexico", "regions": "core", "pay_percent": 90, "payments_since": "2026-11-01"},
                           {"country": "Chile", "regions": "all", "pay_percent": 50, "payments_since": "2026-12-01"}]}
        out = ns["preview_changes"](data, cur, new)
        self.assertTrue(any("100% → 90%" in l and "1,000.00 → 900.00" in l for l in out))
        self.assertTrue(any("Chile: new agreement" in l for l in out))
        self.assertEqual(ns["preview_changes"](data, cur, cur), [])
        self.assertTrue(any("removed" in l for l in ns["preview_changes"](data, cur, {})))


@unittest.skipUnless(AppTest, "needs streamlit")
class SettingsAgreements(unittest.TestCase):
    def run_settings(self, tweak):
        src = open(os.path.join(ROOT, "streamlit_app.py")).read()
        src = src[:src.index("# Temporarily hidden")].replace("HERE = Path(__file__).parent", f"HERE = Path({ROOT!r})") + tweak + "\nsettings()\n"
        at = AppTest.from_string(src, default_timeout=60)
        at.run()
        self.assertFalse(at.exception, [e.message for e in at.exception])
        return at

    def test_agreements_show_first_without_token(self):
        at = self.run_settings("")
        labels = [m.label for m in at.multiselect]
        self.assertTrue(labels[0].startswith("Ireland:"), labels[:3])
        self.assertEqual(at.multiselect[0].value, ["Mexico", "United Kingdom"])

    def test_unreadable_file_falls_back_and_blocks_saving(self):
        at = self.run_settings("import urllib.error\n_has_token = lambda: True\n"
                               "def _gh(*a, **k): raise urllib.error.HTTPError('u', 404, 'nf', {}, None)\n")
        self.assertEqual(at.multiselect[0].value, ["Mexico", "United Kingdom"])
        self.assertTrue(any("Couldn't read agreements.json" in w.value for w in at.warning))
        self.assertEqual([b.label for b in at.button if b.label == "Save agreements"], [])


class SaveErrors(unittest.TestCase):
    def test_plain_reasons(self):
        import urllib.error
        src = open(os.path.join(os.path.dirname(__file__), "..", "streamlit_app.py")).read()
        ns = {}
        exec(src[src.index("def explain_save_error"):src.index("def token_status")], ns)
        f = ns["explain_save_error"]
        mk = lambda c: urllib.error.HTTPError("u", c, "x", {}, None)
        self.assertIn("expired", f(mk(401)))
        self.assertIn("Contents", f(mk(403)))
        self.assertIn("Reload", f(mk(409)))
        self.assertIn("Reload", f(mk(422)))
        self.assertIn("GitHub is having problems", f(mk(502)))
        self.assertIn("Couldn't reach", f(urllib.error.URLError("down")))
        self.assertEqual(f(ValueError("odd")), "odd")


class PageInlining(unittest.TestCase):
    """The Streamlit app inlines the data files into each page (a page run from a string can't fetch them)."""

    def load_page(self):
        import json, pathlib, re, types
        src = open(os.path.join(ROOT, "streamlit_app.py"), encoding="utf-8").read()
        start = re.search(r"@st\.cache_data\(ttl=\d+\)\ndef page", src).start(); end = src.index("def show(")
        st = types.SimpleNamespace(cache_data=lambda **kw: (lambda f: f))
        ns = {"st": st, "json": json, "re": re, "HERE": pathlib.Path(ROOT)}
        exec(src[start:end], ns)
        return ns["page"]

    def test_battle_and_transfer_parts_are_inlined(self):
        page = self.load_page()
        index = page("index.html")
        self.assertIn("window.WE_FILES=", index)
        self.assertIn('"statsP"', index.split("window.WE_FILES=", 1)[1][:200])   # the battle data is there
        self.assertIn('"donors"', page("transfers.html").split("window.WE_FILES=", 1)[1][:200])
        self.assertNotIn("window.WE_FILES=", page("status.html"))   # pages that don't use them don't carry them
