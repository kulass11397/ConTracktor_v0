import tempfile
import unittest
from pathlib import Path

from app import Database, cents, hash_pin, money, verify_pin


class ContractorTrackerTests(unittest.TestCase):
    def test_money_helpers(self):
        self.assertEqual(cents("1,234.56"), 123456)
        self.assertEqual(money(123456), "1,234.56")

    def test_pin_hashing(self):
        salt, digest = hash_pin("2468")
        self.assertTrue(verify_pin("2468", salt, digest))
        self.assertFalse(verify_pin("0000", salt, digest))

    def test_project_creates_default_phases(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            project_id = db.create_project({
                "name": "Test Build", "client": "Test Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "2026-12-01", "notes": "",
            })
            count = db.one("SELECT COUNT(*) count FROM phases WHERE project_id=?", (project_id,))["count"]
            self.assertEqual(count, 9)
            db.close()


if __name__ == "__main__":
    unittest.main()
