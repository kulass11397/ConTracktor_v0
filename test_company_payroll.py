import sqlite3
import unittest
from unittest.mock import patch
from pathlib import Path
from app import Database, hash_pin
import test_project_funding as fixtures

class CompanyPayrollTests(unittest.TestCase):
    setUp=fixtures.ProjectFundingTests.setUp
    attendance=fixtures.ProjectFundingTests.attendance
    advance=fixtures.ProjectFundingTests.advance
    expense=fixtures.ProjectFundingTests.expense

    def test_one_row_combines_project_wages_and_deductions(self):
        self.attendance(self.oasis,60000)
        self.attendance(self.grace,40000,'2026-09-15')
        self.advance(50000)
        rows=self.db.company_weekly_payroll_summary('2026-09-18')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['gross_cents'],100000)
        self.assertEqual(rows[0]['deduction_cents'],50000)
        self.assertEqual(rows[0]['net_cents'],50000)
        self.assertIn('Oasis',rows[0]['project_name'])
        self.assertIn('Grace',rows[0]['project_name'])

    def test_no_attendance_employee_remains_visible(self):
        self.advance(50000)
        row=self.db.company_weekly_payroll_summary('2026-09-18')[0]
        self.assertEqual(row['attendance_count'],0)
        self.assertEqual(row['deduction_cents'],0)

    def test_all_project_advance_export_matches_view(self):
        import app
        self.advance(50000)
        self.db.execute("UPDATE cash_advances SET project_id=?,repayment_plan='Salary Deduction'",(self.grace,))
        with patch.object(app,'write_cash_advance_pdf') as writer:
            app.export_cash_advance_pdf(self.db,None,['Salary Deduction'],'unused.pdf')
            self.assertEqual(writer.call_args.args[3]['advanced'],50000)
            self.assertEqual(writer.call_args.args[3]['count'],1)
            app.export_cash_advance_pdf(self.db,self.oasis,['Salary Deduction'],'unused.pdf')
            self.assertEqual(writer.call_args.args[3]['advanced'],0)

    def test_archived_attendance_not_lost(self):
        self.attendance(self.grace,40000)
        self.db.execute('UPDATE employees SET active=0 WHERE id=?',(self.employee,))
        row=self.db.company_weekly_payroll_summary('2026-09-18')[0]
        self.assertEqual(row['gross_cents'],40000)

    def test_company_numbering_and_aliases_preserve_identity(self):
        aid=self.attendance(self.oasis,60000)
        before=dict(self.db.one('SELECT * FROM attendance WHERE id=?',(aid,)))
        self.db._migrate_company_employee_numbers()
        row=self.db.one('SELECT * FROM employees WHERE id=?',(self.employee,))
        self.assertTrue(row['employee_no'].startswith('MONCON-'))
        self.assertEqual(self.db.employee_for_clock(self.grace,'EMP1','2026-09-18')['id'],self.employee)
        self.assertEqual(self.db.employee_for_clock(self.oasis,row['employee_no'],'2026-09-18')['id'],self.employee)
        self.assertEqual(before,dict(self.db.one('SELECT * FROM attendance WHERE id=?',(aid,))))
        backup=self.db.moncon_migration_backup
        self.assertTrue(backup.exists())
        with sqlite3.connect(backup) as c:
            self.assertEqual(c.execute('SELECT employee_no FROM employees WHERE id=?',(self.employee,)).fetchone()[0],'EMP1')
        c.close()
        numbers=[self.db.next_employee_number(pid) for pid in self.projects]
        self.assertEqual(len(set(numbers)),1)
        self.db._migrate_company_employee_numbers()
        self.assertIsNone(self.db.moncon_migration_backup)

    def test_duplicate_site_numbers_become_unique(self):
        salt,digest=hash_pin('0000')
        second=self.db.execute("INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name) VALUES(?,'EMP1',?,?,'Second')",(self.grace,salt,digest)).lastrowid
        self.db._migrate_company_employee_numbers()
        refs=[r['employee_no'] for r in self.db.all('SELECT employee_no FROM employees')]
        self.assertEqual(len(refs),len(set(refs)))
        self.assertEqual(self.db.one('SELECT id FROM employees WHERE id=?',(second,))['id'],second)

    def test_existing_moncon_collision_is_handled(self):
        salt,digest=hash_pin('0000')
        self.db.execute("INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name) VALUES(?,?,?,?,'Second')",(self.grace,f'MONCON-{self.employee:03d}',salt,digest))
        self.db._migrate_company_employee_numbers()
        refs=[r['employee_no'] for r in self.db.all('SELECT employee_no FROM employees')]
        self.assertEqual(len(refs),len(set(refs)))

    def test_committing_one_site_does_not_repeat_deduction(self):
        self.attendance(self.oasis,60000)
        self.attendance(self.grace,40000,'2026-09-15')
        self.advance(50000)
        self.db.commit_weekly_payroll(self.oasis,'2026-09-18',self.heads[0])
        row=self.db.company_weekly_payroll_summary('2026-09-18')[0]
        self.assertEqual(row['gross_cents'],40000)
        self.assertEqual(row['deduction_cents'],20000)

if __name__=='__main__':unittest.main()
