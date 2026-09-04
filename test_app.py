import tempfile
import unittest
import sqlite3
import zipfile
from pathlib import Path
from unittest.mock import patch

import app as app_module
from app import (Database, PayrollTab, cents, hash_pin, money, resolve_db_path,
                 verify_pin, payroll_week_bounds, write_expense_ledger_pdf,
                 write_simple_pdf, write_payroll_batch_pdf, read_expense_import_form,
                 write_expense_import_form, write_expense_import_xlsx,
                 cash_allocation_approval_mode, EXPENSE_IMPORT_REQUIRED_FIELDS)


class ContractorTrackerTests(unittest.TestCase):
    def test_direct_procurement_uses_single_issuer_approval(self):
        self.assertEqual(cash_allocation_approval_mode("Direct Procurement"), "Single Issuer")
        self.assertEqual(cash_allocation_approval_mode("Petty Cash"), "Two Heads")

    def test_inventory_consumables_track_opening_restock_and_employee_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "inventory-consumables.db")
            project_id = db.create_project({
                "name": "Inventory Project", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "Site", "notes": "",
                "heads": [{"name": "Inventory Head", "position": "Manager", "pin": "0000"}],
            })
            head = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_id,))
            salt, digest = hash_pin("1111")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,position,
                   class,pay_basis,rate_cents,daily_rate_cents,standard_hours)
                   VALUES(?,?,?,?,?,'Painter','Skilled','Daily',80000,80000,'8')""",
                (project_id, "INV-EMP-001", salt, digest, "Employee One"),
            ).lastrowid
            registered = db.register_inventory_item(
                project_id=project_id, name="Interior Paint", material_type="Consumable",
                category="Finishing", unit="liters", opening_quantity_milli=10_000,
                reorder_level_milli=3_000, condition_status="Good", notes="White",
                authorized_by_head_id=head["id"], registration_date="2026-08-26",
            )
            self.assertTrue(registered["item_code"].startswith("INV-"))
            self.assertTrue(registered["reference"].startswith("STK-20260826-"))
            db.record_inventory_movement(
                item_id=registered["id"], transaction_type="Restock", quantity_milli=5_500,
                transaction_date="2026-08-26", reason="Delivery received", notes="",
                authorized_by_head_id=head["id"],
            )
            usage_ref = db.record_inventory_movement(
                item_id=registered["id"], transaction_type="Consume", quantity_milli=12_500,
                transaction_date="2026-08-26", reason="Paint second-floor walls", notes="",
                employee_id=employee_id, authorized_by_head_id=head["id"],
            )
            self.assertTrue(usage_ref.startswith("USE-20260826-"))
            balance = db.inventory_item_balance(registered["id"])
            self.assertEqual(balance["on_hand_milli"], 3_000)
            self.assertEqual(balance["status"], "Low Stock")
            with self.assertRaisesRegex(ValueError, "currently in stock"):
                db.record_inventory_movement(
                    item_id=registered["id"], transaction_type="Consume", quantity_milli=3_001,
                    transaction_date="2026-08-26", reason="Excess issue", notes="",
                    employee_id=employee_id, authorized_by_head_id=head["id"],
                )
            transaction = db.one(
                "SELECT * FROM inventory_transactions WHERE reference=?", (usage_ref,)
            )
            self.assertEqual(transaction["employee_id"], employee_id)
            self.assertEqual(transaction["reason"], "Paint second-floor walls")
            db.revise_inventory_transaction(
                transaction["id"], quantity_milli=11_000,
                transaction_date="2026-08-27", reason="Corrected issue quantity",
                condition_note="", notes="Verified against issue slip",
                correction_reason="Encoding correction",
                authorized_by_head_id=head["id"],
            )
            corrected = db.one(
                "SELECT * FROM inventory_transactions WHERE id=?", (transaction["id"],)
            )
            self.assertEqual(corrected["quantity_milli"], 11_000)
            self.assertEqual(corrected["revision_count"], 1)
            self.assertEqual(db.inventory_item_balance(registered["id"])["on_hand_milli"], 4_500)
            db.edit_inventory_item(
                registered["id"], name="Interior Acrylic Paint", category="Finishing",
                unit="liters", reorder_level_milli=2_000, condition_status="Good",
                notes="White", correction_reason="Correct product name",
                authorized_by_head_id=head["id"],
            )
            self.assertEqual(
                db.one("SELECT name FROM inventory_items WHERE id=?", (registered["id"],))["name"],
                "Interior Acrylic Paint",
            )
            self.assertEqual(
                db.one("SELECT COUNT(*) n FROM audit_log WHERE action='INVENTORY_TRANSACTION_EDITED'")["n"],
                1,
            )
            db.close()

    def test_inventory_tools_track_borrower_returns_and_completed_project_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "inventory-tools.db")
            project_id = db.create_project({
                "name": "Tool Project", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "Site", "notes": "",
                "heads": [{"name": "Tool Head", "position": "Manager", "pin": "0000"}],
            })
            head = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_id,))
            salt, digest = hash_pin("1111")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,position,
                   class,pay_basis,rate_cents,daily_rate_cents,standard_hours)
                   VALUES(?,?,?,?,?,'Carpenter','Skilled','Daily',90000,90000,'8')""",
                (project_id, "TOOL-EMP-001", salt, digest, "Employee Two"),
            ).lastrowid
            registered = db.register_inventory_item(
                project_id=project_id, name="Electric Drill", material_type="Non-Consumable",
                category="Power Tools", unit="unit", opening_quantity_milli=2_000,
                reorder_level_milli=0, condition_status="Good", notes="",
                authorized_by_head_id=head["id"], registration_date="2026-08-26",
            )
            borrow_ref = db.record_inventory_movement(
                item_id=registered["id"], transaction_type="Borrow", quantity_milli=2_000,
                transaction_date="2026-08-26", reason="Install ceiling frames", notes="",
                employee_id=employee_id, condition_note="Good",
                authorized_by_head_id=head["id"],
            )
            loan = db.one("SELECT * FROM inventory_transactions WHERE reference=?", (borrow_ref,))
            self.assertEqual(db.inventory_item_balance(registered["id"])["status"], "Borrowed")
            db.record_inventory_movement(
                item_id=registered["id"], transaction_type="Return", quantity_milli=1_000,
                transaction_date="2026-08-26", reason="One drill returned", notes="",
                employee_id=employee_id, condition_note="Good", linked_transaction_id=loan["id"],
                authorized_by_head_id=head["id"],
            )
            active = db.active_inventory_loans(project_id)
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["outstanding_milli"], 1_000)
            db.record_inventory_movement(
                item_id=registered["id"], transaction_type="Return", quantity_milli=1_000,
                transaction_date="2026-08-26", reason="Final drill returned", notes="",
                employee_id=employee_id, condition_note="Good", linked_transaction_id=loan["id"],
                authorized_by_head_id=head["id"],
            )
            self.assertEqual(db.active_inventory_loans(project_id), [])
            self.assertEqual(db.inventory_item_balance(registered["id"])["available_milli"], 2_000)
            db.complete_project(project_id, "2026-08-26", "Inventory returned", [head])
            with self.assertRaisesRegex(ValueError, "completed project"):
                db.record_inventory_movement(
                    item_id=registered["id"], transaction_type="Borrow", quantity_milli=1_000,
                    transaction_date="2026-08-26", reason="Late issue", notes="",
                    employee_id=employee_id, authorized_by_head_id=head["id"],
                )
            db.close()

    def test_project_completion_preserves_records_and_supports_reactivation(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "project-completion.db")
            project_id = db.create_project({
                "name": "Project Complete", "client": "Client", "contract_value": "100000",
                "start_date": "2026-01-01", "target_date": "2026-08-31",
                "address": "Site", "notes": "Original notes",
                "heads": [{"name": "Head One", "position": "Manager", "pin": "0000"}],
            })
            head = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_id,))
            db.execute("""INSERT INTO remittances(project_id,type,amount_cents,txn_date)
                VALUES(?,'Deposit',10000000,'2026-01-02')""", (project_id,))
            expense_id = db.execute("""INSERT INTO expenses(project_id,name,expense_date,
                total_cents,status,verification_status) VALUES(?,'Closeout expense','2026-08-20',
                2500000,'Partially Paid','Verified')""", (project_id,)).lastrowid
            db.execute("""INSERT INTO payments(expense_id,amount_cents,payment_date,method)
                VALUES(?,1500000,'2026-08-20','Cash')""", (expense_id,))
            before = {
                table: db.one(f"SELECT COUNT(*) n FROM {table}")["n"]
                for table in ("projects", "expenses", "payments", "remittances")
            }

            reference = db.complete_project(
                project_id, "2026-08-25", "Turned over to client", [head]
            )
            self.assertTrue(reference.startswith("CMP-20260825-"))
            self.assertFalse(db.project_is_active(project_id))
            snapshot = db.one(
                "SELECT * FROM project_completion_snapshots WHERE completion_reference=?",
                (reference,),
            )
            self.assertEqual(snapshot["deposited_cents"], 10000000)
            self.assertEqual(snapshot["active_expense_cents"], 2500000)
            self.assertEqual(snapshot["paid_cents"], 1500000)
            self.assertEqual(snapshot["outstanding_cents"], 1000000)
            after = {
                table: db.one(f"SELECT COUNT(*) n FROM {table}")["n"]
                for table in ("projects", "expenses", "payments", "remittances")
            }
            self.assertEqual(before, after)
            self.assertTrue(db.one(
                "SELECT 1 FROM audit_log WHERE project_id=? AND action='PROJECT_COMPLETED'",
                (project_id,),
            ))

            db.reactivate_project(project_id, "Additional client work", [head])
            self.assertTrue(db.project_is_active(project_id))
            self.assertTrue(db.one(
                "SELECT reactivated_at FROM project_completion_snapshots WHERE id=?",
                (snapshot["id"],),
            )["reactivated_at"])
            db.close()

    def test_project_completion_blocks_open_or_uncommitted_attendance(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "project-completion-blocker.db")
            project_id = db.create_project({
                "name": "Open Attendance", "client": "Client", "contract_value": "1000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
                "heads": [{"name": "Head", "position": "Manager", "pin": "0000"}],
            })
            head = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_id,))
            salt, digest = hash_pin("1111")
            employee_id = db.execute("""INSERT INTO employees(project_id,employee_no,pin_salt,
                pin_hash,name,position,rate_cents,daily_rate_cents)
                VALUES(?,?,?,?,?,'Laborer',80000,80000)""",
                (project_id, "OPEN-001", salt, digest, "Employee"),
            ).lastrowid
            db.execute("""INSERT INTO attendance(employee_id,project_id,clock_in,clock_out)
                VALUES(?,?,'2026-08-25T08:00:00','')""", (employee_id, project_id))
            with self.assertRaisesRegex(ValueError, "still clocked in"):
                db.complete_project(project_id, "2026-08-25", "Closeout", [head])
            db.execute("""UPDATE attendance SET clock_out='2026-08-25T17:00:00' WHERE employee_id=?""",
                       (employee_id,))
            with self.assertRaisesRegex(ValueError, "not been committed"):
                db.complete_project(project_id, "2026-08-25", "Closeout", [head])
            db.close()

    def test_employee_transfer_archive_and_attendance_correction_are_audited(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "employee-history.db")
            project_one = db.create_project({
                "name": "Project One", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
                "heads": [{"name": "Head One", "position": "Manager", "pin": "0000"}],
            })
            project_two = db.create_project({
                "name": "Project Two", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
                "heads": [{"name": "Head Two", "position": "Manager", "pin": "0000"}],
            })
            head_one = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_one,))
            head_two = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_two,))
            salt, digest = hash_pin("1111")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,position,
                   class,pay_basis,rate_cents,daily_rate_cents,standard_hours)
                   VALUES(?,?,?,?,?,'Laborer','Labor','Daily',80000,80000,'8')""",
                (project_one, "ONE-001", salt, digest, "Employee One"),
            ).lastrowid
            db.execute(
                """INSERT INTO employee_project_assignments(employee_id,project_id,effective_from,
                   position,daily_rate_cents,reason) VALUES(?,?,?,?,?,'Initial')""",
                (employee_id, project_one, "2026-08-01", "Laborer", 80000),
            )
            attendance_id = db.execute(
                """INSERT INTO attendance(employee_id,project_id,clock_in,clock_out,hours,
                   lunch_hours,regular_hours,overtime_hours,regular_pay_cents,overtime_pay_cents,
                   gross_cents,source) VALUES(?,?,? ,?,'8.00','1.00','8.00','0.00',80000,0,80000,'Manual Batch')""",
                (employee_id, project_one, "2026-08-08T08:00:00", "2026-08-08T17:00:00"),
            ).lastrowid

            db.transfer_employee(employee_id, project_two, "2026-08-09", "Reassignment",
                                 "Laborer", 80000, head_one["id"], head_two["id"])
            self.assertEqual(db.one("SELECT project_id FROM employees WHERE id=?", (employee_id,))["project_id"], project_two)
            self.assertEqual(db.one("SELECT project_id FROM attendance WHERE id=?", (attendance_id,))["project_id"], project_one)

            correction = db.revise_attendance(
                attendance_id, app_module.datetime.fromisoformat("2026-08-08T13:00:00"),
                app_module.datetime.fromisoformat("2026-08-08T17:00:00"),
                "Corrected afternoon shift", head_one["id"],
            )
            self.assertEqual(correction["gross_cents"], 40000)
            self.assertEqual(db.one("SELECT revision_count FROM attendance WHERE id=?", (attendance_id,))["revision_count"], 1)

            db.archive_employee(employee_id, "Project completed", head_two["id"])
            self.assertEqual(db.one("SELECT active FROM employees WHERE id=?", (employee_id,))["active"], 0)
            db.reactivate_employee(employee_id, project_one, "2026-08-10", "Rehired",
                                   "Laborer", 85000, head_one["id"])
            self.assertEqual(db.one("SELECT active FROM employees WHERE id=?", (employee_id,))["active"], 1)
            self.assertEqual(db.one("SELECT COUNT(*) n FROM employee_project_assignments WHERE employee_id=?", (employee_id,))["n"], 3)
            self.assertEqual(db.one("SELECT COUNT(*) n FROM attendance_revisions WHERE attendance_id=?", (attendance_id,))["n"], 1)
            db.close()

    def test_employee_can_be_deployed_to_multiple_projects_without_transfer(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "multi-project-employee.db")
            project_one = db.create_project({
                "name": "Home Project", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
                "heads": [{"name": "Home Head", "position": "Manager", "pin": "0000"}],
            })
            project_two = db.create_project({
                "name": "Second Project", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
                "heads": [{"name": "Second Head", "position": "Manager", "pin": "0000"}],
            })
            head_two = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_two,))
            salt, digest = hash_pin("1111")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,position,
                   class,pay_basis,rate_cents,daily_rate_cents,standard_hours)
                   VALUES(?,?,?,?,?,'Laborer','Labor','Daily',80000,80000,'8')""",
                (project_one, "HOME-001", salt, digest, "Shared Employee"),
            ).lastrowid
            db.execute(
                """INSERT INTO employee_project_assignments(employee_id,project_id,effective_from,
                   position,daily_rate_cents,reason) VALUES(?,?,?,?,?,'Initial')""",
                (employee_id, project_one, "2026-08-01", "Laborer", 80000),
            )

            db.deploy_employee(employee_id, project_two, "2026-08-29", "Finisher", 95000,
                               "Shared across active sites", head_two["id"])

            self.assertEqual(
                db.one("SELECT project_id FROM employees WHERE id=?", (employee_id,))["project_id"],
                project_one,
            )
            self.assertEqual(
                db.one("""SELECT COUNT(*) n FROM employee_project_assignments
                           WHERE employee_id=? AND effective_to=''""", (employee_id,))["n"],
                2,
            )
            deployed = db.employees_deployed_to(project_two, on_date="2026-08-29")
            self.assertEqual([row["id"] for row in deployed], [employee_id])
            self.assertEqual(app_module.employee_daily_rate(deployed[0]), 95000)
            self.assertEqual(db.employee_daily_rate_at(
                employee_id, "2026-08-29", project_one), 80000)
            self.assertEqual(db.employee_daily_rate_at(
                employee_id, "2026-08-29", project_two), 95000)
            self.assertEqual(
                db.one("SELECT COUNT(*) n FROM audit_log WHERE action='EMPLOYEE_DEPLOYED'")["n"], 1
            )
            with self.assertRaisesRegex(ValueError, "already deployed"):
                db.deploy_employee(employee_id, project_two, "2026-08-29", "Finisher", 95000,
                                   "Duplicate", head_two["id"])
            db.close()

    def test_paid_payroll_attendance_correction_queues_next_week_adjustment(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "paid-correction.db")
            project_id = db.create_project({
                "name": "Project Paid", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
                "heads": [{"name": "Payroll Head", "position": "Manager", "pin": "0000"}],
            })
            head = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_id,))
            salt, digest = hash_pin("1111")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,position,
                   class,pay_basis,rate_cents,daily_rate_cents,standard_hours)
                   VALUES(?,?,?,?,?,'Laborer','Labor','Daily',80000,80000,'8')""",
                (project_id, "PAID-001", salt, digest, "Paid Employee"),
            ).lastrowid
            db.execute("""INSERT INTO employee_project_assignments(employee_id,project_id,
                effective_from,position,daily_rate_cents,reason) VALUES(?,?,?,?,?,'Initial')""",
                (employee_id, project_id, "2026-08-01", "Laborer", 80000))
            expense_id = db.execute("""INSERT INTO expenses(project_id,name,total_cents,
                unit_price_cents,expense_date,status) VALUES(?,'Weekly Payroll',80000,80000,
                '2026-08-15','Paid')""", (project_id,)).lastrowid
            batch_id = db.execute("""INSERT INTO payroll_batches(project_id,batch_ref,period_start,
                period_end,gross_cents,deduction_cents,net_cents,expense_id,authorized_by_head_id)
                VALUES(?,'PAYW-TEST-0001','2026-08-15','2026-08-21',80000,0,80000,?,?)""",
                (project_id, expense_id, head["id"])).lastrowid
            attendance_id = db.execute("""INSERT INTO attendance(employee_id,project_id,clock_in,
                clock_out,hours,lunch_hours,regular_hours,overtime_hours,regular_pay_cents,
                overtime_pay_cents,gross_cents,payroll_batch_id,committed_expense_id)
                VALUES(?,?,'2026-08-15T08:00:00','2026-08-15T17:00:00','8.00','1.00',
                '8.00','0.00',80000,0,80000,?,?)""",
                (employee_id, project_id, batch_id, expense_id)).lastrowid
            db.execute("""INSERT INTO payments(expense_id,amount_cents,payment_date,method)
                VALUES(?,80000,'2026-08-15','Cash')""", (expense_id,))

            result = db.revise_attendance(
                attendance_id, app_module.datetime.fromisoformat("2026-08-15T13:00:00"),
                app_module.datetime.fromisoformat("2026-08-15T17:00:00"),
                "Correct afternoon-only shift", head["id"],
            )
            self.assertTrue(result["locked_adjustment"])
            self.assertEqual(db.one("SELECT gross_cents FROM payroll_batches WHERE id=?", (batch_id,))["gross_cents"], 80000)
            adjustment = db.one("SELECT * FROM payroll_adjustments WHERE source_attendance_id=?", (attendance_id,))
            self.assertEqual(adjustment["amount_cents"], -40000)
            self.assertEqual(adjustment["status"], "Pending")
            db.close()

    def test_attendance_correction_can_override_rate_and_exact_final_pay(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "pay-override.db")
            project_id = db.create_project({
                "name": "Rate Override", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
                "heads": [{"name": "Payroll Head", "position": "Manager", "pin": "0000"}],
            })
            head = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_id,))
            salt, digest = hash_pin("1111")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,position,
                   class,pay_basis,rate_cents,daily_rate_cents,standard_hours)
                   VALUES(?,?,?,?,?,'Laborer','Labor','Daily',80000,80000,'8')""",
                (project_id, "RATE-001", salt, digest, "Rate Employee"),
            ).lastrowid
            db.execute("""INSERT INTO employee_project_assignments(employee_id,project_id,
                effective_from,position,daily_rate_cents,reason) VALUES(?,?,?,?,?,'Initial')""",
                (employee_id, project_id, "2026-08-01", "Laborer", 80000))
            attendance_id = db.execute(
                """INSERT INTO attendance(employee_id,project_id,clock_in,clock_out,hours,
                   lunch_hours,regular_hours,overtime_hours,regular_pay_cents,overtime_pay_cents,
                   gross_cents,pay_rate_cents,source)
                   VALUES(?,?,'2026-08-27T08:00:00','2026-08-27T17:00:00','8.00','1.00',
                   '8.00','0.00',80000,0,80000,80000,'Manual Batch')""",
                (employee_id, project_id),
            ).lastrowid
            result = db.revise_attendance(
                attendance_id, app_module.datetime.fromisoformat("2026-08-27T08:00:00"),
                app_module.datetime.fromisoformat("2026-08-27T17:00:00"),
                "Approved day-rate exception", head["id"],
                daily_rate_cents=100000, final_gross_cents=90000,
            )
            self.assertEqual(result["computed_gross_cents"], 100000)
            self.assertEqual(result["gross_cents"], 90000)
            self.assertEqual(result["manual_pay_adjustment_cents"], -10000)
            attendance = db.one("SELECT * FROM attendance WHERE id=?", (attendance_id,))
            self.assertEqual(attendance["pay_rate_cents"], 100000)
            self.assertEqual(attendance["manual_pay_adjustment_cents"], -10000)
            revision = db.one(
                "SELECT * FROM attendance_revisions WHERE attendance_id=?", (attendance_id,)
            )
            self.assertEqual(revision["new_pay_rate_cents"], 100000)
            self.assertEqual(revision["new_manual_adjustment_cents"], -10000)
            db.close()

    def test_void_cash_advance_reverses_payment_and_keeps_audit_history(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "void-advance.db")
            project_id = db.create_project({
                "name": "Advance Void", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
                "heads": [{"name": "Advance Head", "position": "Manager", "pin": "0000"}],
            })
            head = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_id,))
            salt, digest = hash_pin("1111")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,position,
                   class,pay_basis,rate_cents,daily_rate_cents,standard_hours)
                   VALUES(?,?,?,?,?,'Laborer','Labor','Daily',80000,80000,'8')""",
                (project_id, "ADV-001", salt, digest, "Advance Employee"),
            ).lastrowid
            bank_id = db.execute(
                """INSERT INTO bank_accounts(bank_name,account_name,account_number,active)
                   VALUES('PBCOM','Operating','0001',1)"""
            ).lastrowid
            db.execute(
                """INSERT INTO remittances(project_id,type,amount_cents,txn_date,bank_account_id)
                   VALUES(?,'Deposit',100000,'2026-08-27',?)""", (project_id, bank_id)
            )
            expense_id = db.execute(
                """INSERT INTO expenses(project_id,name,total_cents,unit_price_cents,
                   expense_date,status) VALUES(?,'CASH ADVANCE - Advance Employee',20000,20000,
                   '2026-08-27','Paid')""", (project_id,)
            ).lastrowid
            db.execute(
                """INSERT INTO payments(expense_id,amount_cents,payment_date,method,
                   bank_account_id,authorized_by_head_id) VALUES(?,20000,'2026-08-27',
                   'Bank Transfer',?,?)""", (expense_id, bank_id, head["id"])
            )
            advance_id = db.execute(
                """INSERT INTO cash_advances(project_id,employee_id,expense_id,original_cents,
                   advance_date,method,bank_account_id,authorized_by_head_id,repayment_plan,
                   system_reference) VALUES(?,?,?,20000,'2026-08-27','Bank Transfer',?,?,
                   'Salary Deduction','CA-20260827-0001')""",
                (project_id, employee_id, expense_id, bank_id, head["id"]),
            ).lastrowid
            db.execute(
                """INSERT INTO cash_advance_transactions(advance_id,txn_type,amount_cents,
                   txn_date,method,posted) VALUES(?,'Advance',20000,'2026-08-27','Bank Transfer',1)""",
                (advance_id,)
            )
            db.execute(
                """INSERT INTO cash_advance_transactions(advance_id,txn_type,amount_cents,
                   txn_date,method,posted) VALUES(?,'Salary Deduction',20000,'2026-08-27',
                   'Salary Deduction',0)""", (advance_id,)
            )
            self.assertEqual(db.bank_balance(bank_id), 80000)
            result = db.void_cash_advance(advance_id, "Incorrect employee", head["id"])
            self.assertEqual(result["amount_cents"], 20000)
            self.assertEqual(db.bank_balance(bank_id), 100000)
            self.assertEqual(db.one("SELECT voided FROM expenses WHERE id=?", (expense_id,))["voided"], 1)
            self.assertEqual(db.one("SELECT accounting_excluded FROM payments WHERE expense_id=?", (expense_id,))["accounting_excluded"], 1)
            advance = db.one("SELECT * FROM cash_advances WHERE id=?", (advance_id,))
            self.assertEqual(advance["voided"], 1)
            self.assertEqual(advance["void_reason"], "Incorrect employee")
            self.assertEqual(db.one("SELECT COUNT(*) n FROM cash_advance_transactions WHERE advance_id=? AND voided=0", (advance_id,))["n"], 0)
            self.assertEqual(db.one("SELECT COUNT(*) n FROM audit_log WHERE action='CASH_ADVANCE_VOIDED'", ())["n"], 1)
            db.close()

    def test_void_cash_advance_recovery_restores_balance_and_surrender_state(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "void-recovery.db")
            project_id = db.create_project({
                "name": "Recovery Void", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
                "heads": [{"name": "Recovery Head", "position": "Manager", "pin": "0000"}],
            })
            head = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_id,))
            salt, digest = hash_pin("1111")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,position,
                   class,pay_basis,rate_cents,daily_rate_cents,standard_hours)
                   VALUES(?,?,?,?,?,'Laborer','Labor','Daily',80000,80000,'8')""",
                (project_id, "REC-001", salt, digest, "Recovery Employee"),
            ).lastrowid
            advance_id = db.execute(
                """INSERT INTO cash_advances(project_id,employee_id,original_cents,
                   advance_date,reason,method,authorized_by_head_id,repayment_plan,
                   system_reference) VALUES(?,?,20000,'2026-08-27','Test','Cash',?,
                   'Cash Repayment','CA-20260827-0002')""",
                (project_id, employee_id, head["id"]),
            ).lastrowid
            db.execute(
                """INSERT INTO cash_advance_transactions(advance_id,txn_type,amount_cents,
                   txn_date,method,posted) VALUES(?,'Advance',20000,'2026-08-27','Cash',1)""",
                (advance_id,),
            )
            recovery_id = db.execute(
                """INSERT INTO cash_advance_transactions(advance_id,txn_type,amount_cents,
                   txn_date,method,reference,authorized_by_head_id,posted)
                   VALUES(?,'Cash Repayment',5000,'2026-08-27','Cash Repayment',
                   'SR-20260827-0001',?,1)""",
                (advance_id, head["id"]),
            ).lastrowid
            db.execute(
                """INSERT INTO cash_repayment_surrenders(reference,advance_transaction_id,
                   advance_id,amount_cents,surrender_date,received_by_head_id,status)
                   VALUES('SR-20260827-0001',?,?,5000,'2026-08-27',?,'Awaiting Deposit')""",
                (recovery_id, advance_id, head["id"]),
            )
            result = db.void_cash_advance_recovery(
                recovery_id, "Incorrect repayment amount", head["id"]
            )
            self.assertEqual(result["amount_cents"], 5000)
            self.assertEqual(
                db.one("SELECT voided FROM cash_advance_transactions WHERE id=?", (recovery_id,))["voided"],
                1,
            )
            self.assertEqual(
                db.one("SELECT status FROM cash_repayment_surrenders WHERE advance_transaction_id=?", (recovery_id,))["status"],
                "Voided",
            )
            recovered = db.one(
                """SELECT COALESCE(SUM(amount_cents),0) total
                   FROM cash_advance_transactions WHERE advance_id=? AND posted=1
                   AND voided=0 AND txn_type<>'Advance'""", (advance_id,),
            )["total"]
            self.assertEqual(recovered, 0)
            self.assertEqual(
                db.one("SELECT COUNT(*) n FROM audit_log WHERE action='CASH_ADVANCE_RECOVERY_VOIDED'")["n"],
                1,
            )
            restored = db.restore_cash_advance_recovery(
                recovery_id, "Recovery was valid", head["id"]
            )
            self.assertEqual(restored["amount_cents"], 5000)
            self.assertEqual(
                db.one("SELECT voided FROM cash_advance_transactions WHERE id=?", (recovery_id,))["voided"],
                0,
            )
            self.assertEqual(
                db.one("SELECT status FROM cash_repayment_surrenders WHERE advance_transaction_id=?", (recovery_id,))["status"],
                "Awaiting Deposit",
            )
            self.assertEqual(
                db.one("SELECT COUNT(*) n FROM audit_log WHERE action='CASH_ADVANCE_RECOVERY_RESTORED'")["n"],
                1,
            )
            db.close()

    def test_allocation_surrender_and_redeposit_can_be_voided_and_restored(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "void-cash-return.db")
            project_id = db.create_project({
                "name": "Cash Return", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
                "heads": [
                    {"name": "Cash Issuer", "position": "Manager", "pin": "0000"},
                    {"name": "Cash Receiver", "position": "Custodian", "pin": "1111"},
                ],
            })
            heads = db.all(
                "SELECT * FROM project_heads WHERE project_id=? ORDER BY id", (project_id,)
            )
            issuer, receiver = heads[0], heads[1]
            bank_id = db.enroll_bank_account({
                "bank_name": "Test Bank", "account_name": "Cash Return Account",
                "account_number": "1234", "notes": "",
            })
            db.execute(
                """INSERT INTO remittances(project_id,bank_account_id,type,amount_cents,
                   txn_date,system_reference) VALUES(?,?,'Withdrawal',50000,
                   '2026-08-27','WD-20260827-0001')""",
                (project_id, bank_id),
            )
            allocation_id = db.create_cash_allocation(
                project_id=project_id, allocation_type="Petty Cash", amount_cents=50000,
                allocation_date="2026-08-27", issuer_head_id=issuer["id"],
                receiver_head_id=receiver["id"], purpose="Site operations",
            )
            returned = db.close_cash_allocation(
                allocation_id, "2026-08-28", receiver["id"], issuer["id"], "Unused cash"
            )
            self.assertEqual(returned, 50000)
            surrender = db.one(
                """SELECT * FROM cash_allocation_transactions
                   WHERE allocation_id=? AND txn_type='Surrendered'""", (allocation_id,)
            )
            self.assertEqual(db.surrendered_awaiting_deposit(), 50000)
            registry_id = issuer["registry_head_id"]
            reference, deposited = db.redeposit_all_surrendered(
                bank_id, "2026-08-29", registry_id, "Returned to bank"
            )
            self.assertEqual(deposited, 50000)
            redeposit = db.one("SELECT * FROM cash_redeposits WHERE reference=?", (reference,))
            self.assertEqual(db.surrendered_awaiting_deposit(), 0)
            with self.assertRaisesRegex(ValueError, "Void redeposit"):
                db.set_allocation_surrender_voided(
                    surrender["id"], True, "Attempt out of order", issuer["id"]
                )

            db.set_cash_redeposit_voided(
                redeposit["id"], True, "Deposit entered incorrectly", registry_id
            )
            self.assertEqual(db.surrendered_awaiting_deposit(), 50000)
            self.assertEqual(db.bank_balance(bank_id), -50000)
            db.set_allocation_surrender_voided(
                surrender["id"], True, "Cash remains with custodian", issuer["id"]
            )
            self.assertEqual(db.surrendered_awaiting_deposit(), 0)
            self.assertEqual(db.allocation_balance(allocation_id), 50000)
            db.set_allocation_surrender_voided(
                surrender["id"], False, "Cash was surrendered", issuer["id"]
            )
            self.assertEqual(db.surrendered_awaiting_deposit(), 50000)
            db.set_cash_redeposit_voided(
                redeposit["id"], False, "Confirmed bank deposit", registry_id
            )
            self.assertEqual(db.surrendered_awaiting_deposit(), 0)
            self.assertEqual(db.bank_balance(bank_id), 0)
            self.assertEqual(
                db.one("SELECT voided FROM cash_redeposits WHERE id=?", (redeposit["id"],))["voided"],
                0,
            )
            db.close()

    def test_withdrawal_fee_repair_keeps_cash_principal_and_committed_surrender_balanced(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "withdrawal-fee-repair.db")
            project_id = db.create_project({
                "name": "Fee Repair", "client": "Client", "contract_value": "500000",
                "start_date": "2026-07-30", "target_date": "", "address": "", "notes": "",
                "heads": [
                    {"name": "Cash Issuer", "position": "Manager", "pin": "0000"},
                    {"name": "Cash Receiver", "position": "Custodian", "pin": "1111"},
                ],
            })
            issuer, receiver = db.all(
                "SELECT * FROM project_heads WHERE project_id=? ORDER BY id", (project_id,)
            )
            bank_id = db.enroll_bank_account({
                "bank_name": "Test Bank", "account_name": "Operating Account",
                "account_number": "4450", "notes": "",
            })
            db.execute(
                """INSERT INTO remittances(project_id,bank_account_id,type,amount_cents,
                   txn_date,system_reference) VALUES(?,?,'Deposit',50000000,
                   '2026-07-30','BD-20260730-0001')""",
                (project_id, bank_id),
            )
            withdrawal_id = db.execute(
                """INSERT INTO remittances(project_id,bank_account_id,type,amount_cents,
                   txn_date,system_reference,shared_cash) VALUES(?,?,'Withdrawal',44504500,
                   '2026-07-30','WD-20260730-0001',1)""",
                (project_id, bank_id),
            ).lastrowid
            allocation_id = db.create_cash_allocation(
                project_id=project_id, allocation_type="Petty Cash", amount_cents=44504500,
                allocation_date="2026-07-30", issuer_head_id=issuer["id"],
                receiver_head_id=receiver["id"], purpose="Site operations",
            )
            expense_id = db.execute(
                """INSERT INTO expenses(project_id,name,total_cents,unit_price_cents,
                   expense_date,status) VALUES(?,'Recorded site expenses',44488400,44488400,
                   '2026-08-07','Paid')""",
                (project_id,),
            ).lastrowid
            db.execute(
                """INSERT INTO payments(expense_id,amount_cents,payment_date,method,
                   cash_allocation_id,authorized_by_head_id)
                   VALUES(?,44488400,'2026-08-07','Cash',?,?)""",
                (expense_id, allocation_id, receiver["id"]),
            )
            old_return = db.close_cash_allocation(
                allocation_id, "2026-08-07", receiver["id"], issuer["id"],
                "Initial surrender before fee correction",
            )
            self.assertEqual(old_return, 16100)  # P161.00
            surrender = db.one(
                """SELECT * FROM cash_allocation_transactions
                   WHERE allocation_id=? AND txn_type='Surrendered' AND voided=0""",
                (allocation_id,),
            )
            with self.assertRaisesRegex(ValueError, "Void any linked"):
                db.reduce_withdrawal_allocations(
                    withdrawal_id, 44500000, "Separate fee", issuer["registry_head_id"]
                )

            db.set_allocation_surrender_voided(
                surrender["id"], True, "Correct withdrawal principal", issuer["id"]
            )
            with db.conn:
                changes = db.reduce_withdrawal_allocations(
                    withdrawal_id, 44500000,
                    "Correct cash principal and separate bank fee",
                    issuer["registry_head_id"],
                )
                db.conn.execute(
                    """UPDATE remittances SET amount_cents=44500000,
                       withdrawal_fee_cents=4500 WHERE id=?""",
                    (withdrawal_id,),
                )
                fee_expense_id = db.sync_withdrawal_fee_expense(
                    withdrawal_id, 4500, issuer["registry_head_id"]
                )

            self.assertEqual(changes[0]["amount_cents"], 4500)
            self.assertEqual(db.allocation_balance(allocation_id), 11600)  # P116.00
            self.assertEqual(db.cash_summary(project_id), (44500000, 44488400, 11600))
            self.assertEqual(db.bank_balance(bank_id), 5495500)
            fee_expense = db.one("SELECT * FROM expenses WHERE id=?", (fee_expense_id,))
            fee_payment = db.one("SELECT * FROM payments WHERE expense_id=?", (fee_expense_id,))
            self.assertEqual(fee_expense["total_cents"], 4500)
            self.assertEqual(fee_expense["area"], "BANK FEES")
            self.assertEqual(fee_payment["amount_cents"], 4500)
            self.assertEqual(fee_payment["method"], "Bank Transfer")

            corrected_return = db.close_cash_allocation(
                allocation_id, "2026-08-07", receiver["id"], issuer["id"],
                "Corrected surrender after separating bank fee",
            )
            self.assertEqual(corrected_return, 11600)
            active_returns = db.all(
                """SELECT amount_cents FROM cash_allocation_transactions
                   WHERE allocation_id=? AND txn_type='Surrendered' AND voided=0""",
                (allocation_id,),
            )
            self.assertEqual([row["amount_cents"] for row in active_returns], [11600])
            self.assertEqual(
                db.one(
                    """SELECT COUNT(*) n FROM audit_log
                       WHERE action='CASH_ALLOCATION_PRINCIPAL_CORRECTED'"""
                )["n"],
                1,
            )
            db.close()

    def test_expense_import_form_round_trip_preserves_metadata_and_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            form_path = Path(folder) / "expense-import.csv"
            write_expense_import_form(form_path, "DRF-20260819-120000")
            text = form_path.read_text(encoding="utf-8-sig")
            text = text.replace("Declared Batch Total (required),\n", "Declared Batch Total (required),1250.00\n")
            text = text.replace("Example: PROJECT OASIS", "PROJECT OASIS", 1)
            form_path.write_text(text, encoding="utf-8-sig")
            metadata, rows = read_expense_import_form(form_path)
            self.assertEqual(metadata["draft_reference"], "DRF-20260819-120000")
            self.assertEqual(metadata["declared_total"], "1250.00")
            self.assertEqual(rows[0]["project"], "PROJECT OASIS")
            self.assertEqual(rows[0]["item"], "Example item")
            self.assertEqual(rows[0]["supplier"], "")
            self.assertNotIn("supplier", EXPENSE_IMPORT_REQUIRED_FIELDS)
            self.assertGreater(rows[0]["source_row"], 0)

    def test_excel_expense_form_contains_dropdowns_and_google_sheets_reference_lists(self):
        with tempfile.TemporaryDirectory() as folder:
            form_path = Path(folder) / "expense-import.xlsx"
            write_expense_import_xlsx(form_path, "DRF-20260819-130000", {
                "projects": ["PROJECT OASIS [#1]"], "suppliers": ["Supplier One"],
                "phases": ["Foundation"], "categories": ["MATERIALS"],
                "statuses": ["Paid", "Partially Paid", "Unpaid"],
                "methods": ["Cash", "Bank Transfer"], "banks": ["PBCOM - Main"],
                "allocations": ["PC-20260819-0001 | Petty Cash | Head | 10,000.00 remaining"],
            })
            with zipfile.ZipFile(form_path) as archive:
                sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
                workbook = archive.read("xl/workbook.xml").decode("utf-8")
                references = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
            self.assertIn("dataValidations", sheet)
            self.assertIn("CashAllocationOptions", sheet)
            self.assertNotIn("SupplierOptions", workbook)
            self.assertNotIn('sqref="D7:D506"', sheet)
            self.assertIn("Supplier (Optional)", sheet)
            self.assertIn('state="hidden"', workbook)
            self.assertIn("PC-20260819-0001", references)
            self.assertNotIn("Supplier One", references)
            metadata, rows = read_expense_import_form(form_path)
            self.assertEqual(metadata["draft_reference"], "DRF-20260819-130000")
            self.assertEqual(rows, [])

    def test_upgrade_creates_both_legacy_and_v120_backups(self):
        with tempfile.TemporaryDirectory() as folder:
            database_path = Path(folder) / "legacy.db"
            connection = sqlite3.connect(database_path)
            connection.execute("CREATE TABLE projects(id INTEGER PRIMARY KEY, name TEXT)")
            connection.execute("INSERT INTO projects(name) VALUES('Preserved')")
            connection.commit(); connection.close()

            db = Database(database_path)
            self.assertIsNotNone(db.migration_backup)
            self.assertIsNotNone(db.v120_migration_backup)
            self.assertTrue(Path(db.migration_backup).exists())
            self.assertTrue(Path(db.v120_migration_backup).exists())
            self.assertEqual(db.one("SELECT name FROM projects WHERE id=1")["name"], "Preserved")
            db.close()

    def test_batch_cash_advance_commits_one_batch_and_individual_records(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "batch.db")
            project_id = db.create_project({
                "name": "Project Oasis", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "notes": "",
                "heads": [{"name": "Head One", "position": "Manager", "pin": "0000"}],
            })
            head = db.one("SELECT * FROM project_heads WHERE project_id=?", (project_id,))
            salt, digest = hash_pin("1111")
            employee_ids = []
            for number, name in (("OASIS-001", "Employee One"), ("OASIS-002", "Employee Two")):
                employee_ids.append(db.execute(
                    """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,
                       position,class,pay_basis,rate_cents,standard_hours)
                       VALUES(?,?,?,?,?,'Laborer','Labor','Daily',80000,'8')""",
                    (project_id, number, salt, digest, name),
                ).lastrowid)
            bank_id = db.enroll_bank_account({
                "bank_name": "Test Bank", "account_name": "Operations",
                "account_number": "1234", "notes": "",
            })
            db.execute(
                """INSERT INTO remittances(project_id,type,amount_cents,txn_date,
                   bank_account_id,purpose) VALUES(?,'Deposit',10000000,'2026-08-08',?,'Funding')""",
                (project_id, bank_id),
            )

            class FakeDialog:
                def __init__(self, _parent, employees, banks, _allocations):
                    bank_name = next(iter(banks))
                    self.result = {
                        "date": "2026-08-12", "method": "Bank Transfer",
                        "bank": bank_name, "allocation": "",
                        "entries": [
                            {"employee_id": employees[0]["id"], "employee": employees[0]["name"],
                             "amount_cents": 50000, "reason": "Wednesday advance",
                             "repayment_plan": "Salary Deduction", "weekly_cap_cents": 25000},
                            {"employee_id": employees[1]["id"], "employee": employees[1]["name"],
                             "amount_cents": 30000, "reason": "Wednesday advance",
                             "repayment_plan": "Cash Repayment", "weekly_cap_cents": 0},
                        ],
                    }

            class FakeApp:
                def __init__(self, selected_project_id):
                    self.project_id = selected_project_id
                def authorize(self, *_args): return head
                def refresh_all(self): pass

            class FakeLists:
                def select(self, _index): pass

            payroll = PayrollTab.__new__(PayrollTab)
            payroll.db = db
            payroll.app = FakeApp(project_id); payroll.lists = FakeLists()
            payroll.require_project = lambda: True
            payroll.wait_window = lambda _window: None
            with patch.object(app_module, "CashAdvanceBatchDialog", FakeDialog), \
                 patch.object(app_module.messagebox, "showinfo"), \
                 patch.object(app_module.messagebox, "showerror") as showerror:
                payroll.grant_cash_advance_batch()
                error_text = showerror.call_args.args[1] if showerror.called else ""
                self.assertFalse(showerror.called, error_text)

            batch = db.one("SELECT * FROM cash_advance_batches")
            self.assertEqual(batch["advance_date"], "2026-08-12")
            self.assertEqual(batch["entry_count"], 2)
            self.assertEqual(batch["total_cents"], 80000)
            advances = db.all("SELECT * FROM cash_advances ORDER BY id")
            self.assertEqual(len(advances), 2)
            self.assertTrue(all(row["batch_id"] == batch["id"] for row in advances))
            self.assertEqual(len({row["system_reference"] for row in advances}), 2)
            self.assertEqual(
                db.one("SELECT COUNT(*) n FROM expenses WHERE name LIKE 'CASH ADVANCE - %'")["n"], 2)
            self.assertEqual(
                db.one("SELECT COUNT(*) n FROM cash_advance_transactions WHERE txn_type='Salary Deduction'")["n"], 1)
            db.close()

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

    def test_project_address_is_stored(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            project_id = db.create_project({
                "name": "Address Build", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "2026-12-01",
                "address": "123 Sample Street, Manila", "notes": "",
            })
            project = db.one("SELECT * FROM projects WHERE id=?", (project_id,))
            self.assertEqual(project["address"], "123 Sample Street, Manila")
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

    def test_registered_head_can_be_assigned_to_multiple_projects(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            registry_id = db.add_registered_head("Jordan Reyes", "Project Manager")
            registered = db.one("SELECT * FROM head_registry WHERE id=?", (registry_id,))
            self.assertTrue(verify_pin("0000", registered["pin_salt"], registered["pin_hash"]))
            project_ids = []
            for index in range(2):
                project_ids.append(db.create_project({
                    "name": f"Registry Project {index}", "client": "Client",
                    "contract_value": "1000", "start_date": "", "target_date": "",
                    "notes": "", "head_ids": [registry_id],
                }))
            heads = db.all(
                "SELECT * FROM project_heads WHERE registry_head_id=? ORDER BY project_id",
                (registry_id,),
            )
            self.assertEqual(len(heads), 2)
            self.assertEqual({row["project_id"] for row in heads}, set(project_ids))
            self.assertTrue(all(verify_pin("0000", row["pin_salt"], row["pin_hash"]) for row in heads))
            db.close()

    def test_project_head_edit_propagates_and_changes_pin(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            registry_id = db.add_registered_head("Original Head", "Manager")
            project_id = db.create_project({
                "name": "Head Edit", "client": "", "contract_value": "1000",
                "start_date": "", "target_date": "", "notes": "",
                "head_ids": [registry_id],
            })
            db.update_registered_head(
                registry_id, "Updated Head", "Senior Manager", "0000", "2468")
            registry = db.one("SELECT * FROM head_registry WHERE id=?", (registry_id,))
            assigned = db.one(
                "SELECT * FROM project_heads WHERE project_id=? AND registry_head_id=?",
                (project_id, registry_id),
            )
            self.assertEqual(registry["name"], "Updated Head")
            self.assertEqual(assigned["position"], "Senior Manager")
            self.assertTrue(verify_pin("2468", registry["pin_salt"], registry["pin_hash"]))
            self.assertTrue(verify_pin("2468", assigned["pin_salt"], assigned["pin_hash"]))
            with self.assertRaisesRegex(ValueError, "current project-head PIN"):
                db.update_registered_head(
                    registry_id, "Wrong", "Manager", "0000", "")
            db.close()

    def test_payroll_weeks_are_saturday_through_friday(self):
        self.assertEqual(payroll_week_bounds("2026-08-08"), ("2026-08-08", "2026-08-14"))
        self.assertEqual(payroll_week_bounds("2026-08-10"), ("2026-08-08", "2026-08-14"))
        self.assertEqual(payroll_week_bounds("2026-08-14"), ("2026-08-08", "2026-08-14"))
        self.assertEqual(payroll_week_bounds("2026-08-15"), ("2026-08-15", "2026-08-21"))

    def test_salary_deduction_plan_excludes_future_advance(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            project_id = db.create_project({
                "name": "Payroll Dates", "client": "", "contract_value": "1000",
                "start_date": "", "target_date": "", "notes": "",
            })
            salt, digest = hash_pin("1234")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,
                   position,class,pay_basis,rate_cents,standard_hours)
                   VALUES(?,?,?,?,?,'Worker','Labor','Daily',60000,'8')""",
                (project_id, "PAY-001", salt, digest, "Worker"),
            ).lastrowid
            advance_id = db.execute(
                """INSERT INTO cash_advances(project_id,employee_id,original_cents,
                   advance_date,repayment_plan) VALUES(?,?,?,?,?)""",
                (project_id, employee_id, 60_000, "2026-08-12", "Salary Deduction"),
            ).lastrowid
            db.execute(
                """INSERT INTO cash_advance_transactions(advance_id,txn_type,
                   amount_cents,txn_date,method,posted) VALUES(?,?,?,?,?,0)""",
                (advance_id, "Salary Deduction", 60_000, "2026-08-12", "Salary Deduction"),
            )
            self.assertEqual(db.salary_deduction_plan(employee_id, 60_000, "2026-08-09"), [])
            eligible = db.salary_deduction_plan(employee_id, 60_000, "2026-08-14")
            self.assertEqual(sum(item["amount_cents"] for item in eligible), 60_000)
            db.close()

    def test_v120_repair_removes_future_advance_from_older_payroll(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            db = Database(path)
            project_id = db.create_project({
                "name": "Repair", "client": "", "contract_value": "1000",
                "start_date": "", "target_date": "", "notes": "",
            })
            salt, digest = hash_pin("1234")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,
                   position,class,pay_basis,rate_cents,standard_hours)
                   VALUES(?,?,?,?,?,'Worker','Labor','Daily',60000,'8')""",
                (project_id, "REP-001", salt, digest, "Repair Worker"),
            ).lastrowid
            expense_id = db.execute(
                """INSERT INTO expenses(project_id,name,expense_date,total_cents,status)
                   VALUES(?,?,?,?,?)""",
                (project_id, "Old payroll", "2026-08-09", 0, "Paid"),
            ).lastrowid
            batch_id = db.execute(
                """INSERT INTO payroll_batches(project_id,batch_ref,period_start,period_end,
                   gross_cents,deduction_cents,net_cents,expense_id)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (project_id, "PAYW-TEST-1", "2026-08-03", "2026-08-09",
                 60_000, 60_000, 0, expense_id),
            ).lastrowid
            db.execute(
                """INSERT INTO attendance(employee_id,clock_in,clock_out,gross_cents,
                   payroll_batch_id) VALUES(?,?,?,?,?)""",
                (employee_id, "2026-08-08T08:00:00", "2026-08-08T17:00:00",
                 60_000, batch_id),
            )
            advance_id = db.execute(
                """INSERT INTO cash_advances(project_id,employee_id,original_cents,
                   advance_date,repayment_plan) VALUES(?,?,?,?,?)""",
                (project_id, employee_id, 60_000, "2026-08-12", "Salary Deduction"),
            ).lastrowid
            db.execute(
                """INSERT INTO cash_advance_transactions(advance_id,txn_type,amount_cents,
                   txn_date,method,payroll_batch_id,posted)
                   VALUES(?,?,?,?,?,?,1)""",
                (advance_id, "Salary Deduction", 60_000, "2026-08-14",
                 "Salary Deduction", batch_id),
            )
            db.execute("DELETE FROM app_metadata WHERE key IN ('schema_version','payroll_date_repair_v120')")
            db.close()
            upgraded = Database(path)
            batch = upgraded.one("SELECT * FROM payroll_batches WHERE id=?", (batch_id,))
            transaction = upgraded.one(
                "SELECT * FROM cash_advance_transactions WHERE advance_id=?",
                (advance_id,),
            )
            self.assertEqual(batch["deduction_cents"], 0)
            self.assertEqual(batch["net_cents"], 60_000)
            self.assertEqual(transaction["posted"], 0)
            self.assertIsNone(transaction["payroll_batch_id"])
            self.assertEqual(upgraded.one("PRAGMA quick_check")[0], "ok")
            upgraded.close()

    def test_legacy_heads_are_imported_and_reset_to_default_pin_once(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            db = Database(path)
            project_id = db.create_project({
                "name": "Legacy Head", "client": "Client", "contract_value": "1000",
                "start_date": "", "target_date": "", "notes": "",
            })
            salt, digest = hash_pin("4826")
            head_id = db.execute(
                """INSERT INTO project_heads(project_id,name,position,pin_salt,pin_hash)
                   VALUES(?,?,?,?,?)""",
                (project_id, "Legacy Manager", "Project Head", salt, digest),
            ).lastrowid
            db.close()

            upgraded = Database(path)
            head = upgraded.one("SELECT * FROM project_heads WHERE id=?", (head_id,))
            registered = upgraded.one(
                "SELECT * FROM head_registry WHERE id=?", (head["registry_head_id"],)
            )
            self.assertTrue(verify_pin("0000", head["pin_salt"], head["pin_hash"]))
            self.assertTrue(verify_pin("0000", registered["pin_salt"], registered["pin_hash"]))
            self.assertFalse(verify_pin("4826", head["pin_salt"], head["pin_hash"]))
            upgraded.close()

    def test_authorization_columns_exist_for_upgraded_databases(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            expense_columns = {row["name"] for row in db.all("PRAGMA table_info(expenses)")}
            payment_columns = {row["name"] for row in db.all("PRAGMA table_info(payments)")}
            remittance_columns = {row["name"] for row in db.all("PRAGMA table_info(remittances)")}
            project_columns = {row["name"] for row in db.all("PRAGMA table_info(projects)")}
            self.assertIn("authorized_by_head_id", expense_columns)
            self.assertIn("bank_account_id", payment_columns)
            self.assertIn("authorized_by_head_id", remittance_columns)
            self.assertIn("authorized_by_registry_id", remittance_columns)
            self.assertIn("shared_cash", remittance_columns)
            self.assertIn("address", project_columns)
            db.close()

    def test_existing_withdrawals_are_migrated_to_shared_cash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            db = Database(path)
            project_id = db.create_project({
                "name": "Cash Pool", "client": "", "contract_value": "1000",
                "start_date": "", "target_date": "", "notes": "",
            })
            withdrawal_id = db.execute(
                """INSERT INTO remittances(project_id,type,amount_cents,txn_date,shared_cash)
                   VALUES(?,?,?,?,0)""",
                (project_id, "Withdrawal", 10_000, "2026-08-09"),
            ).lastrowid
            db.close()
            upgraded = Database(path)
            row = upgraded.one("SELECT * FROM remittances WHERE id=?", (withdrawal_id,))
            self.assertEqual(row["shared_cash"], 1)
            upgraded.close()

    def test_resolve_db_path_reuses_existing_project_database(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            existing = base / "contractor_tracker.db"
            existing.write_text("placeholder", encoding="utf-8")
            resolved = resolve_db_path(base / "new_app_dir")
            self.assertEqual(resolved, existing)

    def test_shared_bank_and_project_budget_calculations(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            project_id = db.create_project({
                "name": "Budget Test", "client": "Client", "contract_value": "1000",
                "start_date": "", "target_date": "", "notes": "",
            })
            bank_id = db.execute(
                "INSERT INTO bank_accounts(bank_name,account_name,account_number) VALUES(?,?,?)",
                ("Test Bank", "Shared", "1234"),
            ).lastrowid
            db.execute(
                "INSERT INTO remittances(project_id,type,amount_cents,txn_date,bank_account_id) VALUES(?,?,?,?,?)",
                (project_id, "Deposit", 100_000, "2026-08-05", bank_id),
            )
            db.execute(
                "INSERT INTO remittances(project_id,type,amount_cents,txn_date,bank_account_id) VALUES(?,?,?,?,?)",
                (project_id, "Withdrawal", 40_000, "2026-08-05", bank_id),
            )
            expense_id = db.execute(
                """INSERT INTO expenses(project_id,name,expense_date,total_cents,status)
                   VALUES(?,?,?,?,?)""", (project_id, "Paid item", "2026-08-05", 30_000, "Paid"),
            ).lastrowid
            db.execute(
                """INSERT INTO payments(expense_id,amount_cents,payment_date,method)
                   VALUES(?,?,?,?)""", (expense_id, 30_000, "2026-08-05", "Cash"),
            )
            self.assertEqual(db.bank_balance(bank_id), 60_000)
            self.assertEqual(db.project_budget(project_id), (100_000, 30_000, 70_000))
            self.assertEqual(db.cash_summary(project_id), (40_000, 30_000, 10_000))
            db.close()

    def test_bank_transfer_and_cash_funding_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            project_id = db.create_project({
                "name": "Funding Test", "client": "", "contract_value": "1000",
                "start_date": "", "target_date": "", "notes": "",
            })
            bank_id = db.execute(
                "INSERT INTO bank_accounts(bank_name,account_name,account_number) VALUES(?,?,?)",
                ("Test Bank", "Shared", "9876"),
            ).lastrowid
            db.execute(
                "INSERT INTO remittances(project_id,type,amount_cents,txn_date,bank_account_id) VALUES(?,?,?,?,?)",
                (project_id, "Deposit", 100_000, "2026-08-06", bank_id),
            )
            db.execute(
                "INSERT INTO remittances(project_id,type,amount_cents,txn_date,bank_account_id) VALUES(?,?,?,?,?)",
                (project_id, "Withdrawal", 40_000, "2026-08-06", bank_id),
            )
            expense_id = db.execute(
                "INSERT INTO expenses(project_id,name,expense_date,total_cents,status) VALUES(?,?,?,?,?)",
                (project_id, "Transfer item", "2026-08-06", 30_000, "Paid"),
            ).lastrowid
            db.execute(
                """INSERT INTO payments(expense_id,amount_cents,payment_date,method,bank_account_id)
                   VALUES(?,?,?,?,?)""", (expense_id, 30_000, "2026-08-06", "Bank Transfer", bank_id),
            )
            self.assertEqual(db.bank_balance(bank_id), 30_000)
            self.assertEqual(db.project_budget(project_id), (100_000, 30_000, 70_000))
            self.assertEqual(db.cash_summary(), (40_000, 0, 40_000))
            db.validate_payment_source(project_id, 30_000, "Cash")
            with self.assertRaisesRegex(ValueError, "cash on hand"):
                db.validate_payment_source(project_id, 40_001, "Cash")
            with self.assertRaisesRegex(ValueError, "bank balance"):
                db.validate_payment_source(project_id, 30_001, "Bank Transfer", bank_id)
            with self.assertRaisesRegex(ValueError, "remaining budget"):
                db.validate_payment_source(project_id, 70_001, "Cash")
            db.close()

    def test_schema_upgrade_preserves_existing_records(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            db = Database(path)
            project_id = db.create_project({
                "name": "Keep Me", "client": "Client", "contract_value": "10",
                "start_date": "", "target_date": "", "notes": "",
            })
            db.execute("INSERT INTO expenses(project_id,name,expense_date) VALUES(?,?,?)",
                       (project_id, "Existing", "2026-08-05"))
            before = db.one("SELECT COUNT(*) count FROM expenses")["count"]
            db.close()
            upgraded = Database(path)
            self.assertEqual(upgraded.one("SELECT COUNT(*) count FROM expenses")["count"], before)
            self.assertTrue(upgraded.one("SELECT 1 FROM expense_categories LIMIT 1"))
            self.assertIn("status", {row["name"] for row in upgraded.all("PRAGMA table_info(expenses)")})
            upgraded.close()

    def test_partial_bank_schema_is_upgraded_without_losing_accounts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            connection = sqlite3.connect(path)
            connection.execute(
                "CREATE TABLE bank_accounts (id INTEGER PRIMARY KEY, bank_name TEXT NOT NULL)"
            )
            connection.execute("INSERT INTO bank_accounts(bank_name) VALUES(?)", ("Existing Bank",))
            connection.commit()
            connection.close()

            upgraded = Database(path)
            columns = {row["name"] for row in upgraded.all("PRAGMA table_info(bank_accounts)")}
            self.assertTrue(
                {"bank_name", "account_name", "account_number", "notes", "active", "created_at"}
                <= columns
            )
            account = upgraded.one("SELECT * FROM bank_accounts WHERE bank_name=?", ("Existing Bank",))
            self.assertIsNotNone(account)
            self.assertEqual(account["account_name"], "")
            self.assertEqual(account["active"], 1)
            upgraded.close()

    def test_bank_enrollment_supports_required_legacy_name_column(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            connection = sqlite3.connect(path)
            connection.execute(
                """CREATE TABLE bank_accounts (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                    bank_name TEXT NOT NULL DEFAULT '', account_number TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1
                )"""
            )
            connection.commit()
            connection.close()

            db = Database(path)
            account_id = db.enroll_bank_account({
                "bank_name": "PBCOM", "account_name": "Oasis Bank",
                "account_number": "00001234", "notes": "Shared account",
            })
            account = db.one("SELECT * FROM bank_accounts WHERE id=?", (account_id,))
            self.assertEqual(account["name"], "Oasis Bank")
            self.assertEqual(account["bank_name"], "PBCOM")
            self.assertEqual(account["account_number"], "00001234")
            with self.assertRaisesRegex(ValueError, "already enrolled"):
                db.enroll_bank_account({
                    "bank_name": "pbcom", "account_name": "Duplicate",
                    "account_number": "00001234", "notes": "",
                })
            db.close()

    def test_pdf_writer_creates_valid_document(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "expenses.pdf"
            write_simple_pdf(path, "Expense Ledger", ["One | 100.00", "Two | 200.00"])
            payload = path.read_bytes()
            self.assertTrue(payload.startswith(b"%PDF-1.4"))
            self.assertTrue(payload.rstrip().endswith(b"%%EOF"))

    def test_expense_table_pdf_has_filters_table_and_footer(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "filtered_expenses.pdf"
            rows = [{
                "project": "Sample Project", "date": "2026-08-09",
                "expense": "Long expense description / specialized installation material",
                "supplier": "Sample Supplier", "area": "MATERIALS",
                "total": "10,000.00", "paid": "2,500.00",
                "outstanding": "7,500.00", "status": "Pending",
                "authorized": "Project Head",
            } for _ in range(35)]
            write_expense_ledger_pdf(
                path,
                [("Project", "All Projects"), ("Status", "Pending"),
                 ("Area", "All Areas"), ("Supplier", "All Suppliers"),
                 ("Search", "installation")],
                ["Filtered expenses 350,000.00", "Cash on-hand 100,000.00"],
                rows,
            )
            payload = path.read_bytes()
            self.assertTrue(payload.startswith(b"%PDF-1.4"))
            self.assertTrue(payload.rstrip().endswith(b"%%EOF"))
            self.assertIn(b"/MediaBox [0 0 842 595]", payload)
            self.assertIn(b"APPLIED FILTERS", payload)
            self.assertIn(b"EXPENSE", payload)
            self.assertIn(b"/ ITEM", payload)
            self.assertIn(b"ConTracktor_v1 | Page 1 of", payload)
            self.assertIn(b"/F1 10 Tf", payload)
            self.assertIn(b"TOTALS BY STATUS", payload)
            self.assertIn(b"PAID SUBTOTAL", payload)
            self.assertIn(b"UNPAID SUBTOTAL", payload)
            self.assertIn(b"PARTIALLY PAID SUBTOTAL", payload)
            self.assertIn(b"OVERALL TOTAL", payload)

    def test_weekly_payroll_pdf_has_summary_details_and_page_footer(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "weekly_payroll.pdf"
            batch = {
                "project": "PROJECT OASIS", "batch_ref": "PAYW-20260810-0001",
                "period_start": "2026-08-08", "period_end": "2026-08-14",
                "authorized_by": "Kent Fajardo", "gross_cents": 3398000,
                "deduction_cents": 60000, "adjustment_cents": 0,
                "net_cents": 3338000,
            }
            summary_rows = [{
                "employee": f"Employee {index:02d}", "number": f"OASIS-{index:03d}",
                "position": "General Laborer", "days": 5, "logs": 5,
                "regular_hours": "40.00", "ot_hours": "0.00",
                "regular_pay": "3,000.00", "ot_pay": "0.00",
                "gross": "3,000.00", "deductions": "0.00",
                "corrections": "0.00", "net": "3,000.00",
            } for index in range(1, 24)]
            detail_rows = [{
                "employee": f"Employee {(index % 8) + 1:02d}", "date": "2026-08-10",
                "time_in": "08:00:00", "time_out": "17:00:00", "lunch": "1.00",
                "regular_hours": "8.00", "ot_hours": "0.00", "rate": "600.00",
                "regular_pay": "600.00", "ot_pay": "0.00", "override": "-",
                "gross": "600.00", "corrections": 0,
            } for index in range(40)]
            write_payroll_batch_pdf(path, batch, summary_rows, detail_rows)
            payload = path.read_bytes()
            self.assertTrue(payload.startswith(b"%PDF-1.4"))
            self.assertTrue(payload.rstrip().endswith(b"%%EOF"))
            self.assertIn(b"/MediaBox [0 0 842 595]", payload)
            self.assertIn(b"EMPLOYEE WEEKLY SUMMARY", payload)
            self.assertIn(b"DAILY ATTENDANCE DETAILS", payload)
            self.assertIn(b"FINANCIAL SUMMARY", payload)
            self.assertIn(b"PAYW-20260810-0001", payload)
            self.assertIn(b"Page 1 of", payload)


if __name__ == "__main__":
    unittest.main()
