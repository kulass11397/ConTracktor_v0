import tempfile
import unittest
from pathlib import Path

from app import Database, cents, hash_pin, money, resolve_db_path, verify_pin


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

    def test_project_heads_are_hashed_and_linked(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            project_id = db.create_project({
                "name": "Head Test", "client": "Client", "contract_value": "50000",
                "start_date": "2026-08-01", "target_date": "2026-10-01", "notes": "",
                "heads": [{"name": "Alex Cruz", "position": "Project Manager", "pin": "4826"}],
            })
            head = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_id,))
            self.assertEqual(head["name"], "Alex Cruz")
            self.assertNotEqual(head["pin_hash"], "4826")
            self.assertTrue(verify_pin("4826", head["pin_salt"], head["pin_hash"]))
            db.close()

    def test_authorization_columns_exist_for_upgraded_databases(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            expense_columns = {row["name"] for row in db.all("PRAGMA table_info(expenses)")}
            remittance_columns = {row["name"] for row in db.all("PRAGMA table_info(remittances)")}
            self.assertIn("authorized_by_head_id", expense_columns)
            self.assertIn("authorized_by_head_id", remittance_columns)
            db.close()

    def test_resolve_db_path_reuses_existing_project_database(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            existing = base / "contractor_tracker.db"
            existing.write_text("placeholder", encoding="utf-8")
            resolved = resolve_db_path(base / "new_app_dir")
            self.assertEqual(resolved, existing)


if __name__ == "__main__":
    unittest.main()
