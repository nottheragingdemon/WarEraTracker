import importlib.util, os, unittest

spec = importlib.util.spec_from_file_location("secret_scan", os.path.join(os.path.dirname(__file__), "..", "scripts", "secret_scan.py"))
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)


class SecretScan(unittest.TestCase):
    def test_finds_the_usual_shapes(self):   # the fake secrets are built from pieces so this file isn't flagged itself
        self.assertTrue(S.scan_text("t = '" + "ghp_" + "a1B2" * 10 + "'"))
        self.assertTrue(S.scan_text("https://discord.com/api/webhooks/" + "1234567890/" + "abcDEF-" * 5))
        self.assertTrue(S.scan_text('API_KEY = "' + "a1b2c3d4" * 4 + '"'))
        self.assertTrue(S.scan_text("https://app/?key=" + "Zx9" * 6))

    def test_ignores_placeholders_and_workflow_secrets(self):
        self.assertEqual(S.scan_text("WARERA_API_KEY: ${{ secrets.WARERA_API_KEY }}"), [])
        self.assertEqual(S.scan_text("open the app with ?key=<DEV_KEY>"), [])
        self.assertEqual(S.scan_text('token = "your-token-goes-here-please-replace"'), [])

    def test_this_repository_is_clean(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assertEqual(S.scan_repo(root), [])


if __name__ == "__main__":
    unittest.main()
