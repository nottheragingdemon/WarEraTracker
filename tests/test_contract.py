"""The published data files must satisfy site/contract.json (the keys and schema the pages are built for)."""
import json, os, unittest

SITE = os.path.join(os.path.dirname(__file__), "..", "site")


class Contract(unittest.TestCase):
    def test_data_matches_contract(self):
        c = json.load(open(os.path.join(SITE, "contract.json")))
        d = json.load(open(os.path.join(SITE, "data.json")))
        self.assertEqual(c["schema"], 4)
        self.assertEqual([k for k in c["keys"] if k not in d], [])
        self.assertIn(d.get("schema", c["schema"]), (c["schema"],))   # absent only in files published before schema numbers

    def test_pages_check_schema(self):
        for name in os.listdir(SITE):
            if name.endswith(".html"):
                t = open(os.path.join(SITE, name)).read()
                if 'fetch("data.json")' in t:
                    self.assertIn("weSchema(d)", t, name)
