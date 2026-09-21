import unittest
import tkinter as tk
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch
import app
import test_project_funding as fixtures


class CompanyBatchTests(unittest.TestCase):
    setUp = fixtures.ProjectFundingTests.setUp

    def segment(self, project, start, end):
        return (self.employee, project, datetime.fromisoformat('2026-09-14T'+start),
                datetime.fromisoformat('2026-09-14T'+end))

    def test_mobile_employee_two_sites_without_prior_assignment(self):
        self.db.execute('DELETE FROM employee_project_assignments WHERE employee_id=?',(self.employee,))
        ids=self.db.record_batch_project_attendance([
            self.segment(self.oasis,'08:00','12:00'),
            self.segment(self.grace,'13:00','17:00')],self.heads[0])
        rows=self.db.all('SELECT * FROM attendance ORDER BY id')
        self.assertEqual(len(ids),2)
        self.assertEqual([r['project_id'] for r in rows],[self.oasis,self.grace])
        self.assertEqual(sum(r['gross_cents'] for r in rows),100000)
        self.assertEqual(sum(float(r['regular_hours']) for r in rows),8)
        self.assertEqual(sum(float(r['overtime_hours']) for r in rows),0)
        for pid,head in zip(self.projects,self.heads):
            if pid!=self.third:self.db.close_attendance_day(pid,'2026-09-14',head)
        fixtures.ProjectFundingTests.advance(self,60000)
        shares=[r for pid in (self.oasis,self.grace) for r in self.db.weekly_payroll_summary(pid,'2026-09-14')]
        self.assertEqual([r['deduction_cents'] for r in shares],[30000,30000])
        self.assertEqual(self.db.company_weekly_payroll_summary('2026-09-14')[0]['net_cents'],40000)

    expense=fixtures.ProjectFundingTests.expense

    def test_overlapping_staged_sites_are_atomic(self):
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            self.db.record_batch_project_attendance([
                self.segment(self.oasis,'08:00','13:00'),
                self.segment(self.grace,'12:30','17:00')],self.heads[0])
        self.assertFalse(self.db.all('SELECT * FROM attendance'))

    def test_overlap_with_existing_other_site_is_rejected(self):
        self.db.record_batch_project_attendance([self.segment(self.oasis,'08:00','12:00')],self.heads[0])
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            self.db.record_batch_project_attendance([self.segment(self.grace,'11:00','17:00')],self.heads[0])
        self.assertEqual(len(self.db.all('SELECT * FROM attendance')),1)

    def test_touching_segments_allowed_and_global_overtime_preserved(self):
        self.db.record_batch_project_attendance([
            self.segment(self.oasis,'07:00','12:00'),
            self.segment(self.grace,'12:00','18:00')],self.heads[0])
        rows=self.db.all('SELECT * FROM attendance')
        self.assertEqual(sum(float(r['regular_hours']) for r in rows),8)
        self.assertEqual(sum(float(r['overtime_hours']) for r in rows),2)

    def test_archived_employee_and_completed_site_rejected(self):
        self.db.execute('UPDATE employees SET active=0 WHERE id=?',(self.employee,))
        with self.assertRaisesRegex(ValueError,'active MONCON'):
            self.db.record_batch_project_attendance([self.segment(self.oasis,'08:00','12:00')],self.heads[0])
        self.db.execute('UPDATE employees SET active=1 WHERE id=?',(self.employee,))
        self.db.execute("UPDATE projects SET status='Completed' WHERE id=?",(self.grace,))
        with self.assertRaisesRegex(ValueError,'active MONCON'):
            self.db.record_batch_project_attendance([self.segment(self.grace,'13:00','17:00')],self.heads[0])

    def page(self):
        return SimpleNamespace(db=self.db,project_id=None,require_project=Mock(side_effect=AssertionError('Header project must not be required')),
            app=SimpleNamespace(authorize_for_project=Mock(return_value={'id':self.heads[0],'name':'Manager'}),
                authorize_registered_head=Mock(return_value={'id':self.heads[0],'name':'Manager'}),refresh_all=Mock()),
            wait_window=Mock(),after=Mock(),lists=SimpleNamespace(select=Mock()))

    def test_batch_attendance_routes_to_weekly_grid_without_project_header(self):
        page=self.page()
        page.open_weekly_attendance_grid=Mock(return_value='opened')
        self.assertEqual(app.PayrollTab.batch_attendance(page),'opened')
        page.open_weekly_attendance_grid.assert_called_once_with()
        page.require_project.assert_not_called()

    def test_company_advance_grant_uses_explicit_funding_not_employee_home(self):
        page=self.page()
        self.db.execute('DELETE FROM employee_project_assignments WHERE employee_id=?',(self.employee,))
        captured={}
        def opened(parent,db,project_id,employees,banks,allocations,initial=None):
            self.assertIsNone(project_id)
            self.assertEqual([e['id'] for e in employees],[self.employee])
            payload=dict(date='2026-09-14',method='Cash Allocation',allocation=next(iter(allocations)),bank='',
                funding_project_id=self.grace,entries=[dict(employee_id=self.employee,employee='Worker',
                    amount_cents=60000,reason='Weekly advance',repayment_plan='Salary Deduction',weekly_cap_cents=0)])
            captured['payload']=payload
            return SimpleNamespace(result=payload)
        with patch.object(app,'CashAdvanceBatchDialog',side_effect=opened),patch.object(app.messagebox,'askyesno',return_value=True),patch.object(app.messagebox,'showinfo'),patch.object(app.messagebox,'showerror') as errors:
            app.PayrollTab.grant_cash_advance_batch(page)
            errors.assert_not_called()
        self.assertEqual(self.db.one('SELECT project_id FROM cash_advances')['project_id'],self.grace)
        self.assertEqual(self.db.one('SELECT project_id FROM expenses')['project_id'],self.grace)
        self.assertEqual(self.db.one('SELECT project_id FROM cash_advance_batches')['project_id'],self.grace)
        self.assertEqual(self.db.allocation_balance(self.allocation),940000)
        self.assertEqual(self.db.one("SELECT posted FROM cash_advance_transactions WHERE txn_type='Salary Deduction'")['posted'],0)

    def test_dialog_company_roster_and_draft_funding_roundtrip(self):
        root=tk.Tk();root.withdraw();self.addCleanup(root.destroy)
        employees=self.db.all('SELECT * FROM employees WHERE active=1')
        dialog=app.CashAdvanceBatchDialog(root,self.db,None,employees,{}, {})
        self.addCleanup(lambda:dialog.destroy() if dialog.winfo_exists() else None)
        self.assertEqual(len(dialog.employee_tree.get_children()),1)
        self.assertEqual(len(dialog.funding_projects),3)
        self.assertEqual(dialog.vars['funding_project'].get(),'')
        label=next(label for label,pid in dialog.funding_projects.items() if pid==self.grace)
        dialog.vars['funding_project'].set(label)
        dialog.employee_tree.selection_set(str(self.employee))
        dialog.vars['amount'].set('600');dialog.vars['reason'].set('Weekly')
        dialog.stage_selected()
        with patch.object(app.messagebox,'showinfo'):
            dialog.save_draft()
        row,payload=self.db.load_workflow_draft(dialog.draft_id,'cash_advance_batch')
        self.assertEqual(row['project_id'],self.grace)
        self.assertEqual(payload['funding_project_id'],self.grace)
        dialog.vars['funding_project'].set('')
        dialog.restore_snapshot(payload)
        self.assertEqual(dialog.vars['funding_project'].get(),label)
        self.assertEqual(len(dialog.staged),1)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM cash_advances')['n'],0)

    def test_cancel_authorization_reopens_same_staged_payload_without_posting(self):
        page=self.page()
        page.app.authorize_registered_head.return_value=None
        payload=dict(date='2026-09-14',method='Cash Allocation',allocation='',bank='',
            funding_project_id=self.grace,entries=[dict(employee_id=self.employee,employee='Worker',
                amount_cents=60000,reason='Weekly advance',repayment_plan='Salary Deduction',weekly_cap_cents=0)])
        def opened(parent,db,project_id,employees,banks,allocations,initial=None):
            payload['allocation']=next(iter(allocations))
            return SimpleNamespace(result=payload)
        with patch.object(app,'CashAdvanceBatchDialog',side_effect=opened),patch.object(app.messagebox,'askyesno',return_value=True):
            app.PayrollTab.grant_cash_advance_batch(page)
        page.after.assert_called_once()
        self.assertIs(page.after.call_args.args[1].__defaults__[0],payload)
        self.assertFalse(self.db.all('SELECT * FROM cash_advances'))
        self.assertEqual(self.db.allocation_balance(self.allocation),1000000)


if __name__=='__main__':unittest.main()
