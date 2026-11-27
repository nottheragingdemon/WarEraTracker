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

    def test_core_stays_core_and_token_and_dryrun_panel(self):
        at = self.run_settings("_has_token = lambda: True\ntoken_status_cached = lambda: ('ok', 'Token works.')\n"
                               "import json as _j, base64 as _b\n"
                               "_f = {'paper_ratio': 0.5, 'agreements': {'Ireland': [{'country': 'Mexico', 'regions': 'core', 'pay_percent': 100, 'payments_since': '2026-11-01'}]}}\n"
                               "_res = {'at': '2026-11-27 10:00 UTC', 'ok': True, 'checked': ['Ireland: 2 partner countries, 846.85 owed so far'], 'problems': []}\n"
                               "def _gh(m, p, body=None): return {'sha': 's', 'content': _b.b64encode(_j.dumps(_res if 'dryrun' in p else _f).encode()).decode()}\n"
                               "def _gh_actions(m, p, body=None): return {'workflow_runs': [{'conclusion': 'success', 'status': 'completed', 'created_at': '2026-11-27T10:00:00Z', 'html_url': 'https://x'}]}\n")
        self.assertTrue(any("846.85 owed so far" in m.value for m in at.markdown))
        self.assertTrue(any("Token works" in s.value for s in at.success))
        self.assertTrue(any("Latest check: success" in s.value for s in at.success))
        self.assertIn("Core regions only (not conquered ones)", [x.value for x in at.selectbox])

    def test_history_panel_lists_versions(self):
        at = self.run_settings("_has_token = lambda: True\ntoken_status_cached = lambda: ('ok', 'Token works.')\n"
                               "import json as _j, base64 as _b\n"
                               "_f = {'paper_ratio': 0.5, 'agreements': {}}\n"
                               "def _gh(m, p, body=None): return {'sha': 's', 'content': _b.b64encode(_j.dumps(_f).encode()).decode()}\n"
                               "def _gh_actions(m, p, body=None): return {'workflow_runs': []}\n"
                               "def _gh_repo(m, p, body=None): return [{'sha': 'aaaaaaaaaaaa', 'commit': {'committer': {'date': '2026-11-27T10:00:00Z'}, 'message': 'Settings: new'}},"
                               " {'sha': 'bbbbbbbbbbbb', 'commit': {'committer': {'date': '2026-11-20T10:00:00Z'}, 'message': 'Settings: old'}}]\n")
        self.assertEqual([b.label for b in at.button if b.label == "Restore this version"], ["Restore this version"])   # not offered for the current one

    def test_published_core_detected(self):
        at = self.run_settings("")
        self.assertIn("Core regions only (not conquered ones)", [x.value for x in at.selectbox])

    def test_unreadable_file_falls_back_and_blocks_saving(self):
        at = self.run_settings("import urllib.error\n_has_token = lambda: True\ntoken_status_cached = lambda: ('ok', 'Token works.')\n"
                               "def _gh(*a, **k): raise urllib.error.HTTPError('u', 404, 'nf', {}, None)\n"
                               "def _gh_actions(*a, **k): raise urllib.error.HTTPError('u', 403, 'no', {}, None)\n")
        self.assertEqual(at.multiselect[0].value, ["Mexico", "United Kingdom"])
        self.assertTrue(any("Couldn't read agreements.json" in w.value for w in at.warning))
        self.assertEqual([b.label for b in at.button if b.label == "Save agreements"], [])


class TokenStatus(unittest.TestCase):
    def test_missing_permissions_are_named(self):
        import io, types, urllib.error
        src = open(os.path.join(os.path.dirname(__file__), "..", "streamlit_app.py")).read()
        ns = {"st": types.SimpleNamespace(secrets={"GITHUB_TOKEN": "t"}), "REPO": "o/r", "AGREEMENTS_PATH": "a.json"}
        exec(src[src.index("def token_status"):src.index("@st.cache_data(ttl=300")], ns)
        class R:
            headers = {"github-authentication-token-expiration": "2099-01-01 00:00:00 UTC"}
            def __enter__(self): return self
            def __exit__(self, *a): return False
        import urllib.request
        orig = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: R()
        try:
            ns["_gh"] = lambda *a, **k: {}
            def no(*a, **k): raise urllib.error.HTTPError("u", 403, "x", {}, None)
            ns["_gh_actions"] = no
            kind, msg = ns["token_status"]()
            self.assertEqual(kind, "warn")
            self.assertIn("Missing permission: Actions", msg)
            ns["_gh_actions"] = lambda *a, **k: {}
            kind, msg = ns["token_status"]()
            self.assertEqual(kind, "ok")
            self.assertNotIn("Missing", msg)
        finally:
            urllib.request.urlopen = orig


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

    def test_guide_carries_only_the_stamp(self):
        page = self.load_page()
        self.assertLess(len(page("guide.html")), 450_000)   # not the whole data file (0.7 MB) on top of the screenshots
        self.assertIn('"generated"', page("guide.html"))

    def test_battle_and_transfer_parts_are_inlined(self):
        page = self.load_page()
        index = page("index.html")
        self.assertIn("window.WE_FILES=", index)
        self.assertIn('"statsP"', index.split("window.WE_FILES=", 1)[1][:200])   # the battle data is there
        self.assertIn('"donors"', page("transfers.html").split("window.WE_FILES=", 1)[1][:200])
        self.assertNotIn("window.WE_FILES=", page("status.html"))   # pages that don't use them don't carry them
