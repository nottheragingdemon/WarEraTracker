"""The artifact copies are generated from site/ by scripts/sync_artifacts.py."""
import importlib.util, json, os, tempfile, unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("sync_artifacts", os.path.join(HERE, "scripts", "sync_artifacts.py"))
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncTests(unittest.TestCase):
    def test_builds_both_artifacts(self):
        with tempfile.TemporaryDirectory() as out:
            info = sync.build(out)
            self.assertEqual(info["tracker"], ["company.html", "data.json", "efficiency.html", "index.html", "status.html", "theme.css", "theme.js", "transfers.html"])
            self.assertEqual(info["ask"], ["ask-data.json", "data.json", "index.html", "theme.css", "theme.js"])
            for page in ("index.html", "company.html", "transfers.html", "efficiency.html", "status.html"):
                html = open(os.path.join(out, "tracker", page), encoding="utf-8").read()
                self.assertNotIn('href="ask.html"', html)
                self.assertIn('class="ext" data-dev>Ask WarEra', html)
            ask = open(os.path.join(out, "ask", "index.html"), encoding="utf-8").read()
            self.assertEqual(ask.count('<a href="index.html" aria-current="page">Ask WarEra</a>'), 1)
            self.assertNotIn("transfers.html", ask.split("</nav>")[0].split('id="apps"')[1])
            self.assertTrue(json.load(open(os.path.join(out, "ask", "data.json")))["generated"])
            self.assertIn("bounty", json.load(open(os.path.join(out, "ask", "ask-data.json"))))

    def test_data_json_is_the_light_file(self):
        d = json.load(open(os.path.join(HERE, "site", "data.json")))
        self.assertNotIn("bounty", d)
        self.assertNotIn("contracts", d)


if __name__ == "__main__":
    unittest.main()
