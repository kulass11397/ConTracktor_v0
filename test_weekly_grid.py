import unittest
import tkinter as tk
from datetime import datetime

import test_project_funding as fixtures
from app import build_expense_billing_context, build_expense_client_summary, WeeklyAttendanceGridDialog


class WeeklyGridTests(unittest.TestCase):
    setUp=fixtures.ProjectFundingTests.setUp

    def test_draft_is_separate_then_finalizes_two_sites(self):
        cells={
            (self.employee,'2026-09-14',self.oasis):{'state':'Present','segments':[['08:00','12:00']]},
            (self.employee,'2026-09-14',self.grace):{'state':'Present','segments':[['13:00','17:00']]},
            (self.employee,'2026-09-15',self.oasis):{'state':'Absent','segments':[]},
        }
        self.assertEqual(self.db.save_weekly_attendance_draft('2026-09-14',cells),3)
        self.assertEqual(self.db.all('SELECT * FROM attendance'),[])
        self.assertEqual(self.db.weekly_attendance_draft('2026-09-14'),cells)
        self.assertEqual(self.db.finalize_weekly_attendance_draft('2026-09-14',
            {self.oasis:self.heads[0],self.grace:self.heads[1]}),2)
        self.assertEqual(len(self.db.all('SELECT * FROM attendance')),2)
        self.assertEqual(len(self.db.all('SELECT * FROM attendance_closure_batches')),2)
        self.assertEqual(len(self.db.all("SELECT * FROM weekly_attendance_marks WHERE state='Absent'")),1)
        self.assertEqual(self.db.weekly_attendance_draft('2026-09-14'),{})
        self.assertEqual(self.db.company_weekly_payroll_summary('2026-09-14')[0]['gross_cents'],100000)

    def test_overlapping_sites_rejected_without_partial_save(self):
        cells={(self.employee,'2026-09-14',self.oasis):{'state':'Present','segments':[['08:00','13:00']]},
               (self.employee,'2026-09-14',self.grace):{'state':'Present','segments':[['12:00','17:00']]}}
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            self.db.save_weekly_attendance_draft('2026-09-14',cells)
        self.assertEqual(self.db.weekly_attendance_draft('2026-09-14'),{})

    def test_existing_attendance_blocks_duplicate_weekly_grid_entry(self):
        self.db.record_batch_project_attendance([(self.employee,self.oasis,
            datetime(2026,9,14,8),datetime(2026,9,14,12))],self.heads[0])
        cells={(self.employee,'2026-09-14',self.grace):{'state':'Present','segments':[['11:00','17:00']]}}
        with self.assertRaisesRegex(ValueError,'overlapping recorded attendance'):
            self.db.save_weekly_attendance_draft('2026-09-14',cells)

    def test_billing_math_is_read_only(self):
        self.db.execute("INSERT INTO expenses(project_id,name,total_cents,expense_date) VALUES(?,'Material',12345,'2026-09-14')",(self.oasis,))
        rows=self.db.all("""SELECT e.*,'' phase,0 payment_total,0 recovery_total,0 cash_advance_id
            FROM expenses e WHERE e.project_id=?""",(self.oasis,))
        before=self.db.conn.total_changes
        context=build_expense_client_summary(self.db,rows,[self.oasis],date_from='2026-09-12',date_to='2026-09-18')
        bill=build_expense_billing_context(self.db,rows,context,'15','Client','Biller')
        self.assertEqual(bill['basis_cents'],12345)
        self.assertEqual(bill['fee_cents'],1852)
        self.assertEqual(bill['overall_cents'],14197)
        self.assertEqual(sum(context['weekly']['2026-09-12 to 2026-09-18'].values()),12345)
        self.assertEqual(self.db.conn.total_changes,before)

    def test_project_tabs_and_company_review_open(self):
        try:
            root=tk.Tk()
        except tk.TclError:
            self.skipTest('Desktop display unavailable')
        root.withdraw()
        try:
            pane=WeeklyAttendanceGridDialog(root,self.db,root,'2026-09-14')
            root.update()
            self.assertEqual(len(pane.trees),4)
            self.assertIn(None,pane.trees)
            self.assertEqual(len(pane.trees[self.oasis].get_children()),1)
            pane.destroy()
        finally:
            root.destroy()


if __name__=='__main__':unittest.main()
