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
