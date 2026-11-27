"""The alliance scope file is found from wherever the stage modules live."""
import os, unittest

from wartrack import db as dbm
from wartrack.stages import common


class ScopeTests(unittest.TestCase):
    def test_scope_file_found(self):
        self.assertTrue(os.path.exists(common.SCOPE_FILE), common.SCOPE_FILE)

    def test_alliance_countries(self):
        db = dbm.connect(":memory:")
        db.execute("INSERT INTO alliances VALUES('a1','The Emerald Accord',NULL)")
        db.execute("INSERT INTO alliance_members VALUES('a1','c1'),('a1','c2')")
        self.assertEqual(common.alliance_countries(db), {"c1", "c2"})


if __name__ == "__main__":
    unittest.main()
