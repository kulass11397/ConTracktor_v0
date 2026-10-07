"""Regression coverage for DP cash restored by expense voids."""
import tempfile
import unittest
from pathlib import Path

from app import Database


class AllocationReactivationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'reactivation.db'
        self.db = Database(self.path)
        self.project = self.db.create_project({
            'name': 'DP Test', 'client': 'Test', 'contract_value': '10000',
            'start_date': '2026-09-01', 'target_date': '', 'address': '', 'notes': '',
            'heads': [{'name': 'Issuer', 'position': 'Manager', 'pin': '0000'},
                      {'name': 'Holder', 'position': 'Custodian', 'pin': '1111'}],
        })
        self.issuer, holder = self.db.all(
            'SELECT * FROM project_heads WHERE project_id=? ORDER BY id', (self.project,))
        withdrawal = self.db.execute(
            """INSERT INTO remittances(project_id,type,amount_cents,txn_date,
               shared_cash,system_reference) VALUES(?,'Withdrawal',200000,
               '2026-09-01',1,'WD-TEST')""", (self.project,)).lastrowid
        self.allocation = self.db.create_cash_allocation(
            project_id=self.project, allocation_type='Direct Procurement',
            amount_cents=100000, allocation_date='2026-09-01',
            issuer_head_id=self.issuer['id'], receiver_head_id=holder['id'],
            supplier='Vendor', purpose='Materials', withdrawal_sources=[(withdrawal, 100000)])
        self.expense = self.db.execute(
            """INSERT INTO expenses(project_id,name,item,total_cents,unit_price_cents,
               expense_date,status) VALUES(?,'Materials','Materials',100000,100000,
               '2026-09-01','Paid')""", (self.project,)).lastrowid
        payment = self.db.execute(
            """INSERT INTO payments(expense_id,amount_cents,payment_date,method,
               cash_allocation_id) VALUES(?,100000,'2026-09-01','Cash',?)""",
            (self.expense, self.allocation)).lastrowid
        with self.db.conn:
            self.db.register_allocation_payment(
                self.allocation, payment, self.expense, 100000, '2026-09-01', self.issuer['id'])

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def status(self):
        return self.db.one('SELECT status,closed_at FROM cash_allocations WHERE id=?',
                           (self.allocation,))

    def test_void_reopens_and_restore_consumes_cash_again(self):
        self.assertEqual(self.status()['status'], 'Completed')
        self.db.set_expense_voided(self.expense, True)
        self.assertEqual(self.status()['status'], 'Active')
        self.assertEqual(self.status()['closed_at'], '')
        self.assertEqual(self.db.allocation_balance(self.allocation), 100000)
        self.assertIn(self.allocation, self.db.active_allocation_options().values())
        self.db.set_expense_voided(self.expense, False)
        self.assertEqual(self.status()['status'], 'Completed')
        self.assertEqual(self.db.allocation_balance(self.allocation), 0)

    def test_restored_cash_can_be_returned_but_not_spent_twice(self):
        self.db.set_expense_voided(self.expense, True)
        self.db.return_cash_allocation_to_pool(
            self.allocation, 100000, '2026-09-02', 'Voided purchase', self.issuer['id'])
        self.assertEqual(self.status()['status'], 'Returned to Shared Pool')
        self.assertEqual(self.db.unallocated_cash(), 200000)
        with self.assertRaises(ValueError):
            self.db.set_expense_voided(self.expense, False)
        self.assertEqual(self.db.one('SELECT voided FROM expenses WHERE id=?',
                                     (self.expense,))['voided'], 1)
        self.assertEqual(self.status()['status'], 'Returned to Shared Pool')

    def test_startup_reopens_legacy_completed_label_idempotently(self):
        self.db.execute('UPDATE expenses SET voided=1 WHERE id=?', (self.expense,))
        self.assertEqual(self.status()['status'], 'Completed')
        self.db.close()
        self.db = Database(self.path)
        self.assertEqual(self.status()['status'], 'Active')
        self.db._reopen_restored_allocations()
        self.assertEqual(self.db.allocation_balance(self.allocation), 100000)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM payments')['n'], 1)

    def test_partial_void_keeps_other_payments_and_reopens_partially_used(self):
        other = self.db.execute(
            """INSERT INTO expenses(project_id,name,total_cents,status,expense_date)
               VALUES(?,'Other purchase',40000,'Paid','2026-09-01')""", (self.project,)).lastrowid
        self.db.execute('UPDATE payments SET amount_cents=60000 WHERE expense_id=?',
                        (self.expense,))
        self.db.execute(
            """INSERT INTO payments(expense_id,amount_cents,payment_date,method,
               cash_allocation_id) VALUES(?,40000,'2026-09-01','Cash',?)""",
            (other, self.allocation))
        self.db.set_expense_voided(self.expense, True)
        self.assertEqual(self.status()['status'], 'Partially Used')
        self.assertEqual(self.db.allocation_balance(self.allocation), 60000)
        self.db.return_cash_allocation_to_pool(
            self.allocation, 60000, '2026-09-02', 'Voided portion', self.issuer['id'])
        self.assertEqual(self.db.allocation_spent(self.allocation), 40000)


if __name__ == '__main__':
    unittest.main()
