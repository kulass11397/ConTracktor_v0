import tempfile
import unittest
import sqlite3
from datetime import datetime
from pathlib import Path

from app import (Database, cents, compute_shift_pay, hash_pin, money, resolve_db_path, verify_pin,
                 payroll_week_bounds, write_expense_ledger_pdf, write_simple_pdf)


class ContractorTrackerTests(unittest.TestCase):
    def test_interbank_transfer_moves_account_balance_without_changing_total_funds(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            project_id = db.create_project({
                "name": "Project Oasis", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
            })
            head_id = db.add_registered_head("Transfer Head", "Treasurer")
            source_id = db.enroll_bank_account({
                "bank_name": "Source Bank", "account_name": "Operating",
                "account_number": "1001", "notes": "",
            })
            destination_id = db.enroll_bank_account({
                "bank_name": "Destination Bank", "account_name": "Materials",
                "account_number": "2002", "notes": "",
            })
            db.execute(
                """INSERT INTO remittances(project_id,type,amount_cents,txn_date,
                   bank_account_id,system_reference) VALUES(?,'Deposit',100000,'2026-08-12',?,'BD-1')""",
                (project_id, source_id),
            )
            result = db.create_bank_account_transfer(
                from_bank_account_id=source_id, to_bank_account_id=destination_id,
                amount_cents=35000, transfer_date="2026-08-12",
                purpose="Allocate materials fund", notes="Test transfer",
                authorized_by_registry_id=head_id,
            )
            self.assertTrue(result["reference"].startswith("IBT-20260812-"))
            self.assertEqual(db.bank_balance(source_id), 65000)
            self.assertEqual(db.bank_balance(destination_id), 35000)
            self.assertEqual(db.bank_balance(source_id) + db.bank_balance(destination_id), 100000)
            transfer = db.one("SELECT * FROM bank_account_transfers WHERE id=?", (result["id"],))
            self.assertEqual(transfer["amount_cents"], 35000)
            self.assertEqual(transfer["authorized_by_registry_id"], head_id)
            db.close()

    def test_employee_number_is_project_derived_and_sequential(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            project_id = db.create_project({
                "name": "Project Oasis", "client": "", "contract_value": "1",
                "start_date": "", "target_date": "", "address": "", "notes": "",
            })
            self.assertEqual(db.next_employee_number(project_id), "OASIS-001")
            salt, digest = hash_pin("0000")
            db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name)
                   VALUES(?,?,?,?,?)""",
                (project_id, "OASIS-001", salt, digest, "First Worker"),
            )
            self.assertEqual(db.next_employee_number(project_id), "OASIS-002")
            db.close()

    def test_daily_closure_accumulates_then_commits_one_weekly_payroll(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            project_id = db.create_project({
                "name": "Weekly Payroll", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
            })
            head_registry = db.add_registered_head("Payroll Head", "Manager")
            db._assign_registered_heads(project_id, [head_registry])
            head = db.project_head_for_registry(head_registry, project_id)
            salt, digest = hash_pin("0000")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,
                   position,class,pay_basis,rate_cents,standard_hours,daily_rate_cents)
                   VALUES(?,?,?,?,?,?,?,'Daily',80000,'8',80000)""",
                (project_id, "WEEK-001", salt, digest, "Weekly Worker", "Carpenter", "Skilled"),
            ).lastrowid
            bank_id = db.execute(
                "INSERT INTO bank_accounts(bank_name,account_name,account_number) VALUES(?,?,?)",
                ("Test Bank", "Payroll", "1001"),
            ).lastrowid
            db.execute(
                """INSERT INTO remittances(project_id,type,amount_cents,txn_date,bank_account_id)
                   VALUES(?,'Deposit',10000000,'2026-08-10',?)""", (project_id, bank_id),
            )
            for work_date in ("2026-08-10", "2026-08-11"):
                db.execute(
                    """INSERT INTO attendance(employee_id,clock_in,clock_out,hours,
                       regular_hours,overtime_hours,gross_cents,source)
                       VALUES(?,?,?,'8.00','8.00','0.00',80000,'Test')""",
                    (employee_id, f"{work_date}T08:00:00", f"{work_date}T17:00:00"),
                )
                closed = db.close_attendance_day(project_id, work_date, head["id"])
                self.assertTrue(closed["reference"].startswith("ATD-"))

            summary = db.weekly_payroll_summary(project_id, "2026-08-12")
            worker = next(row for row in summary if row["id"] == employee_id)
            self.assertEqual(payroll_week_bounds("2026-08-12"),
                             ("2026-08-10", "2026-08-16"))
            self.assertEqual(worker["attendance_count"], 2)
            self.assertEqual(worker["gross_cents"], 160000)
            result = db.commit_weekly_payroll(project_id, "2026-08-12", head["id"])
            self.assertTrue(result["reference"].startswith("PAYW-"))
            self.assertEqual(result["attendance_count"], 2)
            employee_summary = db.payroll_batch_employee_summary(result["id"])
            self.assertEqual(len(employee_summary), 1)
            self.assertEqual(employee_summary[0]["name"], "Weekly Worker")
            self.assertEqual(employee_summary[0]["attendance_days"], 2)
            self.assertEqual(employee_summary[0]["attendance_entries"], 2)
            self.assertEqual(employee_summary[0]["regular_hours"], 16.0)
            self.assertEqual(employee_summary[0]["gross_cents"], 160000)
            self.assertEqual(employee_summary[0]["deduction_cents"], 0)
            self.assertEqual(db.one(
                "SELECT COUNT(*) n FROM attendance WHERE payroll_batch_id=?",
                (result["id"],),
            )["n"], 2)
            expense = db.one("SELECT * FROM expenses WHERE id=?", (result["expense_id"],))
            self.assertEqual(expense["total_cents"], 160000)
            self.assertIn("Weekly Payroll", expense["name"])
            db.close()

    def test_weekly_payroll_uses_net_pay_and_does_not_double_count_salary_deduction(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            project_id = db.create_project({
                "name": "Net Payroll", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
            })
            registry_id = db.add_registered_head("Net Payroll Head", "Manager")
            db._assign_registered_heads(project_id, [registry_id])
            head = db.project_head_for_registry(registry_id, project_id)
            salt, digest = hash_pin("0000")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,
                   position,class,pay_basis,rate_cents,standard_hours,daily_rate_cents)
                   VALUES(?,?,?,?,?,?,?,'Daily',80000,'8',80000)""",
                (project_id, "NET-001", salt, digest, "Net Worker", "Laborer", "Labor"),
            ).lastrowid
            bank_id = db.execute(
                "INSERT INTO bank_accounts(bank_name,account_name,account_number) VALUES('Bank','Payroll','001')"
            ).lastrowid
            db.execute(
                """INSERT INTO remittances(project_id,type,amount_cents,txn_date,bank_account_id)
                   VALUES(?,'Deposit',10000000,'2026-08-10',?)""", (project_id, bank_id),
            )
            advance_id = db.execute(
                """INSERT INTO cash_advances(project_id,employee_id,original_cents,advance_date,
                   reason,method,repayment_plan) VALUES(?,?,80000,'2026-08-10',
                   'Test advance','Cash','Salary Deduction')""", (project_id, employee_id),
            ).lastrowid
            db.execute(
                """INSERT INTO cash_advance_transactions(advance_id,txn_type,amount_cents,
                   txn_date,method,posted) VALUES(?,'Salary Deduction',80000,
                   '2026-08-10','Salary Deduction',0)""", (advance_id,),
            )
            for work_date in ("2026-08-10", "2026-08-11"):
                db.execute(
                    """INSERT INTO attendance(employee_id,clock_in,clock_out,hours,
                       regular_hours,overtime_hours,gross_cents,source)
                       VALUES(?,?,?,'8.00','8.00','0.00',80000,'Test')""",
                    (employee_id, f"{work_date}T08:00:00", f"{work_date}T17:00:00"),
                )
                db.close_attendance_day(project_id, work_date, head["id"])

            result = db.commit_weekly_payroll(project_id, "2026-08-12", head["id"])
            expense = db.one("SELECT * FROM expenses WHERE id=?", (result["expense_id"],))
            self.assertEqual(result["gross_cents"], 160000)
            self.assertEqual(result["deduction_cents"], 80000)
            self.assertEqual(result["net_cents"], 80000)
            self.assertEqual(expense["total_cents"], 80000)
            self.assertEqual(db.one(
                "SELECT COUNT(*) n FROM payments WHERE expense_id=?",
                (result["expense_id"],),
            )["n"], 0)
            deduction = db.one(
                "SELECT * FROM cash_advance_transactions WHERE advance_id=? AND txn_type='Salary Deduction'",
                (advance_id,),
            )
            self.assertEqual(deduction["posted"], 1)
            self.assertEqual(deduction["payroll_batch_id"], result["id"])
            db.close()

    def test_historical_cash_repayment_migrates_once_to_surrendered_cash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            db = Database(path)
            project_id = db.create_project({
                "name": "Surrender Migration", "client": "", "contract_value": "1000",
                "start_date": "", "target_date": "", "address": "", "notes": "",
            })
            salt, digest = hash_pin("0000")
            employee_id = db.execute(
                "INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name) VALUES(?,?,?,?,?)",
                (project_id, "SR-001", salt, digest, "Repaying Worker"),
            ).lastrowid
            advance_id = db.execute(
                """INSERT INTO cash_advances(project_id,employee_id,original_cents,
                   advance_date,reason,method) VALUES(?,?,10000,'2026-08-13','Test','Cash')""",
                (project_id, employee_id),
            ).lastrowid
            transaction_id = db.execute(
                """INSERT INTO cash_advance_transactions(advance_id,txn_type,amount_cents,
                   txn_date,method,posted) VALUES(?,'Cash Repayment',10000,
                   '2026-08-13','Cash Repayment',1)""", (advance_id,),
            ).lastrowid
            db.close()

            migrated = Database(path)
            surrender = migrated.one(
                "SELECT * FROM cash_repayment_surrenders WHERE advance_transaction_id=?",
                (transaction_id,),
            )
            self.assertIsNotNone(surrender)
            self.assertEqual(surrender["amount_cents"], 10000)
            self.assertEqual(surrender["status"], "Awaiting Deposit")
            self.assertEqual(migrated.surrendered_awaiting_deposit(), 10000)
            migrated.close()

            reopened = Database(path)
            self.assertEqual(reopened.one(
                "SELECT COUNT(*) n FROM cash_repayment_surrenders WHERE advance_transaction_id=?",
                (transaction_id,),
            )["n"], 1)
            reopened.close()

    def test_employee_compliance_and_embedded_photo_columns_are_additive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            db = Database(path)
            project_id = db.create_project({
                "name": "People", "client": "", "contract_value": "1",
                "start_date": "", "target_date": "", "address": "", "notes": "",
            })
            salt, digest = hash_pin("0000")
            photo = b"\x89PNG\r\n\x1a\nportable-photo"
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,
                   nbi_clearance,police_clearance,drug_test,biodata,photo_data,
                   photo_filename,photo_mime)
                   VALUES(?,?,?,?,?,1,0,1,1,?,'worker.png','image/png')""",
                (project_id, "PIC-001", salt, digest, "Photo Worker", photo),
            ).lastrowid
            db.close()
            reopened = Database(path)
            row = reopened.one("SELECT * FROM employees WHERE id=?", (employee_id,))
            self.assertEqual(row["nbi_clearance"], 1)
            self.assertEqual(row["police_clearance"], 0)
            self.assertEqual(row["drug_test"], 1)
            self.assertEqual(row["biodata"], 1)
            self.assertEqual(row["photo_data"], photo)
            reopened.close()

    def test_shift_pay_excludes_lunch_and_applies_125_percent_overtime(self):
        ordinary = compute_shift_pay(
            datetime(2026, 8, 10, 8), datetime(2026, 8, 10, 17), 80000
        )
        self.assertEqual(ordinary["lunch_hours"], "1.00")
        self.assertEqual(ordinary["regular_hours"], "8.00")
        self.assertEqual(ordinary["overtime_hours"], "0.00")
        self.assertEqual(ordinary["gross_cents"], 80000)

        overtime = compute_shift_pay(
            datetime(2026, 8, 10, 8), datetime(2026, 8, 10, 19), 80000
        )
        self.assertEqual(overtime["hours"], "10.00")
        self.assertEqual(overtime["overtime_hours"], "2.00")
        self.assertEqual(overtime["regular_pay_cents"], 80000)
        self.assertEqual(overtime["overtime_pay_cents"], 25000)
        self.assertEqual(overtime["gross_cents"], 105000)

    def test_payroll_and_cash_advance_schema_is_additive(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            tables = {
                row["name"] for row in db.all(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue({
                "payroll_batches", "cash_advances", "cash_advance_transactions"
            }.issubset(tables))
            self.assertTrue({
                "cash_allocations", "cash_allocation_transactions",
                "expense_verification_batches", "expense_verification_items",
                "expense_verification_approvals",
            }.issubset(tables))
            employee_columns = {
                row["name"] for row in db.all("PRAGMA table_info(employees)")
            }
            attendance_columns = {
                row["name"] for row in db.all("PRAGMA table_info(attendance)")
            }
            self.assertTrue({
                "birthday", "contact_number", "daily_rate_cents"
            }.issubset(employee_columns))
            self.assertTrue({
                "lunch_hours", "regular_hours", "overtime_hours",
                "regular_pay_cents", "overtime_pay_cents", "payroll_batch_id"
            }.issubset(attendance_columns))
            db.close()

    def test_withdrawal_allocations_payments_surrender_and_verification_reconcile(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            project_id = db.create_project({
                "name": "Oasis Allocation Test", "client": "Client",
                "contract_value": "500000", "start_date": "2026-08-01",
                "target_date": "", "address": "", "notes": "",
            })
            salt, digest = hash_pin("0000")
            first_head = db.execute(
                """INSERT INTO project_heads(project_id,name,position,pin_salt,pin_hash)
                   VALUES(?,?,?,?,?)""",
                (project_id, "Ali Taps", "Project Head", salt, digest),
            ).lastrowid
            salt, digest = hash_pin("0000")
            second_head = db.execute(
                """INSERT INTO project_heads(project_id,name,position,pin_salt,pin_hash)
                   VALUES(?,?,?,?,?)""",
                (project_id, "Kent Fajardo", "Project Head", salt, digest),
            ).lastrowid
            db.execute(
                "INSERT INTO remittances(project_id,type,amount_cents,txn_date) VALUES(?,?,?,?)",
                (project_id, "Deposit", 30000000, "2026-08-01"),
            )
            withdrawal_id = db.execute(
                """INSERT INTO remittances(project_id,type,amount_cents,txn_date,shared_cash)
                   VALUES(?,?,?,?,1)""",
                (project_id, "Withdrawal", 10000000, "2026-08-02"),
            ).lastrowid
            allocation_id = db.create_cash_allocation(
                withdrawal_id=withdrawal_id, project_id=project_id,
                allocation_type="Petty Cash", amount_cents=6000000,
                allocation_date="2026-08-02", issuer_head_id=first_head,
                receiver_head_id=second_head, purpose="Site purchases",
            )
            self.assertEqual(db.withdrawal_available(withdrawal_id), 4000000)
            self.assertEqual(db.unallocated_cash(), 4000000)
            db.create_cash_allocation(
                withdrawal_id=withdrawal_id, project_id=project_id,
                allocation_type="Petty Cash", amount_cents=2000000,
                allocation_date="2026-08-02", issuer_head_id=first_head,
                receiver_head_id=second_head, purpose="Second active fund",
            )
            with self.assertRaisesRegex(ValueError, "two active petty-cash"):
                db.create_cash_allocation(
                    withdrawal_id=withdrawal_id, project_id=project_id,
                    allocation_type="Petty Cash", amount_cents=1000000,
                    allocation_date="2026-08-02", issuer_head_id=first_head,
                    receiver_head_id=second_head, purpose="Third active fund",
                )
            expense_id = db.execute(
                """INSERT INTO expenses(project_id,name,item,qty,unit,unit_price_cents,
                   total_cents,expense_date,status,default_cash_allocation_id)
                   VALUES(?,?,?,'1','lot',?,?,?,'Partially Paid',?)""",
                (project_id, "Roof supplies", "Roof supplies", 5000000, 5000000,
                 "2026-08-03", allocation_id),
            ).lastrowid
            payment_id = db.execute(
                """INSERT INTO payments(expense_id,amount_cents,payment_date,method,
                   authorized_by_head_id,cash_allocation_id) VALUES(?,?,?,'Cash',?,?)""",
                (expense_id, 2000000, "2026-08-03", first_head, allocation_id),
            ).lastrowid
            db.register_allocation_payment(
                allocation_id, payment_id, expense_id, 2000000,
                "2026-08-03", first_head,
            )
            self.assertEqual(db.allocation_balance(allocation_id), 4000000)
            self.assertEqual(db.cash_summary()[2], 8000000)
            self.assertEqual(db.unallocated_cash(), 2000000)
            verification = db.verify_expense_batch(
                project_id, [expense_id], [first_head, second_head],
                "2026-08-04", "Weekly regroup",
            )
            self.assertTrue(verification.startswith("VF-"))
            self.assertEqual(
                db.one("SELECT verification_status FROM expenses WHERE id=?", (expense_id,))[0],
                "Verified",
            )
            returned = db.close_cash_allocation(
                allocation_id, "2026-08-05", second_head, first_head, "Fund surrendered"
            )
            self.assertEqual(returned, 4000000)
            # Surrendered cash is locked until it is deposited back to a bank;
            # it must never silently become spendable unallocated cash again.
            self.assertEqual(db.unallocated_cash(), 2000000)
            self.assertEqual(db.surrendered_awaiting_deposit(), 4000000)
            bank_id = db.execute(
                """INSERT INTO bank_accounts(bank_name,account_name,account_number)
                   VALUES('Test Bank','Operating','0001')"""
            ).lastrowid
            reference, deposited = db.redeposit_all_surrendered(
                bank_id, "2026-08-05", None, "Automatic full surrender deposit"
            )
            self.assertTrue(reference.startswith("RD-"))
            self.assertEqual(deposited, 4000000)
            self.assertEqual(db.surrendered_awaiting_deposit(), 0)
            self.assertEqual(db.cash_summary()[2], 4000000)
            db.close()

    def test_cash_advance_recovery_reconciles_project_and_cash_balances(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            project_id = db.create_project({
                "name": "Recovery Test", "client": "Client",
                "contract_value": "5000", "start_date": "2026-08-01",
                "target_date": "", "notes": "",
            })
            db.execute(
                "INSERT INTO remittances(project_id,type,amount_cents,txn_date) VALUES(?,?,?,?)",
                (project_id, "Deposit", 200000, "2026-08-01"),
            )
            db.execute(
                "INSERT INTO remittances(project_id,type,amount_cents,txn_date) VALUES(?,?,?,?)",
                (project_id, "Withdrawal", 50000, "2026-08-01"),
            )
            salt, digest = hash_pin("1234")
            employee_id = db.execute(
                """INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,
                   position,class,pay_basis,rate_cents,standard_hours,daily_rate_cents)
                   VALUES(?,?,?,?,?,?,?,'Daily',?,8,?)""",
                (project_id, "REC-001", salt, digest, "Test Employee",
                 "Carpenter", "Skilled", 80000, 80000),
            ).lastrowid
            expense_id = db.execute(
                """INSERT INTO expenses(project_id,name,item,qty,unit,unit_price_cents,
                   total_cents,area,expense_date,status)
                   VALUES(?,?,?,'1','advance',?,?,?,?,'Paid')""",
                (project_id, "CASH ADVANCE - TEST EMPLOYEE",
                 "CASH ADVANCE - TEST EMPLOYEE", 50000, 50000,
                 "PAYROLL", "2026-08-01"),
            ).lastrowid
            db.execute(
                """INSERT INTO payments(expense_id,amount_cents,payment_date,method)
                   VALUES(?,?,?,'Cash')""",
                (expense_id, 50000, "2026-08-01"),
            )
            advance_id = db.execute(
                """INSERT INTO cash_advances(project_id,employee_id,expense_id,
                   original_cents,advance_date,reason,method)
                   VALUES(?,?,?,?,?,?,'Cash')""",
                (project_id, employee_id, expense_id, 50000,
                 "2026-08-01", "Emergency advance"),
            ).lastrowid
            db.execute(
                """INSERT INTO cash_advance_transactions(advance_id,txn_type,
                   amount_cents,txn_date,method,posted)
                   VALUES(?,'Advance',?,?,'Cash',1)""",
                (advance_id, 50000, "2026-08-01"),
            )
            db.execute(
                """INSERT INTO cash_advance_transactions(advance_id,txn_type,
                   amount_cents,txn_date,method,posted)
                   VALUES(?,'Cash Repayment',?,?,'Cash Repayment',1)""",
                (advance_id, 10000, "2026-08-08"),
            )

            self.assertEqual(db.project_budget(project_id), (200000, 40000, 160000))
            self.assertEqual(
                db.project_commitment_budget(project_id), (200000, 40000, 160000)
            )
            self.assertEqual(db.cash_summary(), (50000, 40000, 10000))
            self.assertEqual(db.expense_recoveries(expense_id), 10000)
            db.close()

    def test_shared_cash_fifo_spans_withdrawals_and_global_head_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            first_project = db.create_project({
                "name": "FIFO One", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
            })
            second_project = db.create_project({
                "name": "FIFO Two", "client": "Client", "contract_value": "100000",
                "start_date": "2026-08-01", "target_date": "", "address": "", "notes": "",
            })
            issuer_registry = db.add_registered_head("Issuer", "Project Head")
            holder_registry = db.add_registered_head("Holder", "Project Head")
            db._assign_registered_heads(first_project, [issuer_registry, holder_registry])
            issuer = db.project_head_for_registry(issuer_registry, first_project)
            holder = db.project_head_for_registry(holder_registry, first_project)
            first_withdrawal = db.execute(
                """INSERT INTO remittances(project_id,type,amount_cents,txn_date,shared_cash,
                   system_reference,transaction_time) VALUES(?,'Withdrawal',4000,'2026-08-01',1,
                   'WD-20260801-0001','2026-08-01 08:00:00')""", (first_project,)
            ).lastrowid
            second_withdrawal = db.execute(
                """INSERT INTO remittances(project_id,type,amount_cents,txn_date,shared_cash,
                   system_reference,transaction_time) VALUES(?,'Withdrawal',3000,'2026-08-02',1,
                   'WD-20260802-0001','2026-08-02 08:00:00')""", (second_project,)
            ).lastrowid
            allocation = db.create_cash_allocation(
                project_id=first_project, allocation_type="Petty Cash", amount_cents=6000,
                allocation_date="2026-08-03", issuer_head_id=issuer["id"],
                receiver_head_id=holder["id"], issuer_registry_id=issuer_registry,
                receiver_registry_id=holder_registry, purpose="Shared projects",
            )
            sources = db.all(
                """SELECT withdrawal_id,amount_cents FROM cash_allocation_sources
                   WHERE allocation_id=? ORDER BY withdrawal_id""", (allocation,)
            )
            self.assertEqual(
                [(row["withdrawal_id"], row["amount_cents"]) for row in sources],
                [(first_withdrawal, 4000), (second_withdrawal, 2000)],
            )
            self.assertEqual(db.withdrawal_available(first_withdrawal), 0)
            self.assertEqual(db.withdrawal_available(second_withdrawal), 1000)
            # A second allocation may use a different legacy project context, but
            # ownership and the two-active-account limit remain global by registry.
            db.create_cash_allocation(
                project_id=second_project, allocation_type="Petty Cash", amount_cents=500,
                allocation_date="2026-08-03", issuer_head_id=issuer["id"],
                receiver_head_id=holder["id"], issuer_registry_id=issuer_registry,
                receiver_registry_id=holder_registry, purpose="Second shared account",
            )
            with self.assertRaisesRegex(ValueError, "two active petty-cash"):
                db.create_cash_allocation(
                    project_id=second_project, allocation_type="Petty Cash", amount_cents=500,
                    allocation_date="2026-08-03", issuer_head_id=issuer["id"],
                    receiver_head_id=holder["id"], issuer_registry_id=issuer_registry,
                    receiver_registry_id=holder_registry, purpose="Third shared account",
                )
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
            self.assertIn("authorized_by_head_id", payment_columns)
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
            db.execute(
                """INSERT INTO expenses(project_id,name,expense_date,total_cents,status)
                   VALUES(?,?,?,?,?)""", (project_id, "Unpaid commitment", "2026-08-05", 20_000, "Unpaid"),
            )
            self.assertEqual(db.bank_balance(bank_id), 60_000)
            self.assertEqual(db.project_budget(project_id), (100_000, 30_000, 70_000))
            self.assertEqual(db.project_commitment_budget(project_id), (100_000, 50_000, 50_000))
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
                "mop": "Bank Transfer",
                "supplier": "Sample Supplier", "area": "MATERIALS",
                "total": "10,000.00", "paid": "2,500.00",
                "outstanding": "7,500.00", "status": "Partially Paid",
                "verification": "Unverified", "allocation": "PC-OASIS-001",
                "withdrawal": "WD-0001",
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
            self.assertIn(b"(EXPENSE)", payload)
            self.assertIn(b"(/ ITEM)", payload)
            self.assertIn(b"(MOP)", payload)
            self.assertIn(b"(VERIF)", payload)
            self.assertIn(b"(CASH)", payload)
            self.assertIn(b"(TOTA)", payload)
            self.assertIn(b"(OUTS)", payload)
            self.assertIn(b"(Bank)", payload)
            self.assertIn(b"(Tran)", payload)
            self.assertIn(b"(PC-)", payload)
            self.assertIn(b"ConTracktor_v1 | Page 1 of", payload)
            self.assertIn(b"/F1 10 Tf", payload)
            self.assertIn(b"TOTALS BY STATUS", payload)
            self.assertIn(b"PAID SUBTOTAL", payload)
            self.assertIn(b"UNPAID SUBTOTAL", payload)
            self.assertIn(b"PARTIALLY PAID SUBTOTAL", payload)
            self.assertIn(b"OVERALL TOTAL", payload)


if __name__ == "__main__":
    unittest.main()
