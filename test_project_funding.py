import json
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app import Database, hash_pin, compute_shift_pay, BulkExpenseDialog


class ProjectFundingTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.db=Database(Path(self.folder.name)/'test.db')
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(self.db.close)
        self.projects=[];self.heads=[]
        for name in ('Oasis','Grace','Third'):
            pid=self.db.create_project(dict(name=name,client='Client',contract_value='100000',
                start_date='2026-01-01',target_date='',address='',notes='',
                heads=[dict(name='Manager',position='Head',pin='0000'),dict(name='Custodian',position='Head',pin='0000')]))
            self.projects.append(pid)
            self.heads.append(self.db.one('SELECT id FROM project_heads WHERE project_id=?',(pid,))['id'])
            self.db.execute("INSERT INTO remittances(project_id,type,amount_cents,txn_date) VALUES(?,'Deposit',10000000,'2026-09-12')",(pid,))
        self.oasis,self.grace,self.third=self.projects
        salt,digest=hash_pin('0000')
        self.employee=self.db.execute("""INSERT INTO employees(project_id,employee_no,pin_salt,pin_hash,name,
            rate_cents,daily_rate_cents) VALUES(?,'EMP1',?,?,'Worker',100000,100000)""",(self.oasis,salt,digest)).lastrowid
        for pid in self.projects:
            self.db.execute("""INSERT INTO employee_project_assignments(employee_id,project_id,effective_from,
                daily_rate_cents) VALUES(?,?,'2026-01-01',100000)""",(self.employee,pid))
        self.withdrawal=self.db.execute("""INSERT INTO remittances(project_id,type,amount_cents,txn_date,
            shared_cash,system_reference) VALUES(?,'Withdrawal',10000000,'2026-09-12',1,'WD-TEST')""",(self.oasis,)).lastrowid
        self.allocation=self.db.create_cash_allocation(project_id=self.oasis,allocation_type='Direct Procurement',
            withdrawal_sources=[(self.withdrawal,1000000)],
            amount_cents=1000000,allocation_date='2026-09-12',issuer_head_id=self.heads[0],
            receiver_head_id=self.db.one("SELECT id FROM project_heads WHERE project_id=? AND name='Custodian'",(self.oasis,))['id'],purpose='Payroll',supplier='Payroll')

    def expense(self,pid,amount=100000):
        return self.db.execute("""INSERT INTO expenses(project_id,name,total_cents,expense_date)
            VALUES(?,'Materials',?,'2026-09-14')""",(pid,amount)).lastrowid

    def attendance(self,pid,amount,day='2026-09-14'):
        result=compute_shift_pay(datetime.fromisoformat(day+'T08:00'),datetime.fromisoformat(day+'T17:00'),amount)
        aid=self.db.execute("""INSERT INTO attendance(employee_id,project_id,clock_in,clock_out,hours,
            regular_hours,overtime_hours,regular_pay_cents,overtime_pay_cents,gross_cents,pay_rate_cents)
            VALUES(?,?,?,?,'8','8','0',?,0,?,?)""",(self.employee,pid,day+'T08:00:00',day+'T17:00:00',amount,amount,amount)).lastrowid
        self.db.close_attendance_day(pid,day,self.heads[self.projects.index(pid)])
        return aid

    def advance(self,amount=100000,cap=0,day='2026-09-13'):
        expense=self.expense(self.oasis,amount)
        self.db.execute("INSERT INTO payments(expense_id,amount_cents,payment_date,method) VALUES(?,?,?,'Cash')",(expense,amount,day))
        advance=self.db.execute("""INSERT INTO cash_advances(project_id,employee_id,expense_id,original_cents,
            advance_date,weekly_deduction_cap_cents) VALUES(?,?,?,?,?,?)""",(self.oasis,self.employee,expense,amount,day,cap)).lastrowid
        self.db.execute("""INSERT INTO cash_advance_transactions(advance_id,txn_type,amount_cents,txn_date,
            method,posted) VALUES(?,'Salary Deduction',?,?,'Salary Deduction',0)""",(advance,amount,day))
        return advance

    def two_project_week(self):
        self.attendance(self.oasis,300000)
        self.attendance(self.grace,200000,'2026-09-15')
        self.advance()

    def commit(self,pid):
        return self.db.commit_weekly_payroll(pid,'2026-09-14',self.heads[self.projects.index(pid)])

    def test_funding_is_one_expense_two_linked_project_views(self):
        eid=self.expense(self.grace)
        before=self.db.cash_summary()[2]
        self.db.record_project_payment(eid,100000,'2026-09-14','Cash',self.heads[0],self.oasis,self.allocation)
        loans=self.db.interproject_loans()
        self.assertEqual(len(loans),1)
        self.assertEqual(self.db.interproject_balance(self.oasis),(100000,0))
        self.assertEqual(self.db.interproject_balance(self.grace),(0,100000))
        self.assertEqual(self.db.project_budget(self.oasis)[2],9900000)
        self.assertEqual(self.db.project_budget(self.grace)[2],10000000)
        self.assertEqual(self.db.cash_summary()[2],before-100000)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM expenses')['n'],1)
        self.assertEqual(self.db.one('SELECT status FROM expenses WHERE id=?',(eid,))['status'],'Paid')

    def test_partial_borrowing_tracks_only_money_actually_paid(self):
        eid=self.expense(self.grace)
        self.db.record_project_payment(eid,40000,'2026-09-14','Cash',self.heads[0],self.oasis,self.allocation)
        self.assertEqual(self.db.interproject_balance(self.grace),(0,40000))
        self.assertEqual(self.db.one('SELECT status FROM expenses WHERE id=?',(eid,))['status'],'Partially Paid')

    def test_repayment_is_not_another_expense_or_supplier_payment(self):
        eid=self.expense(self.grace)
        self.db.record_project_payment(eid,100000,'2026-09-14','Cash',self.heads[0],self.oasis,self.allocation)
        loan=self.db.interproject_loans()[0]
        before=self.db.cash_summary()
        self.db.repay_project_funding(loan['id'],40000,'2026-09-16',self.heads[1],'SETTLE-1')
        self.assertEqual(self.db.interproject_balance(self.grace),(0,60000))
        self.assertEqual(self.db.project_budget(self.oasis)[2],9940000)
        self.assertEqual(self.db.project_budget(self.grace)[2],9960000)
        self.assertEqual(self.db.cash_summary(),before)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM expenses')['n'],1)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM payments')['n'],1)
        with self.assertRaises(ValueError):self.db.assert_funding_reversal_allowed(eid)

    def test_cash_receipt_batch_repayment_moves_project_cash_and_keeps_company_cash(self):
        receipt=self.db.execute("""INSERT INTO remittances(project_id,type,amount_cents,txn_date,
            cash_received,system_reference,purpose) VALUES(?,'Deposit',200000,'2026-09-15',1,
            'CR-20260915-0001','Client reimbursement cash')""",(self.grace,)).lastrowid
        first=self.expense(self.grace,100000)
        second=self.expense(self.grace,50000)
        self.db.record_project_payment(first,100000,'2026-09-14','Cash',self.heads[0],self.oasis,self.allocation)
        self.db.record_project_payment(second,50000,'2026-09-14','Cash',self.heads[0],self.oasis,self.allocation)
        loans=self.db.interproject_loans(self.grace)
        company_before=self.db.cash_summary()[2]
        grace_before=self.db.cash_summary(self.grace)[2]
        oasis_before=self.db.cash_summary(self.oasis)[2]
        result=self.db.repay_project_funding_batch([row['id'] for row in loans],
            '2026-09-16',self.heads[1],'CLIENT-CASH','Two reviewed costs','Cash Receipt',receipt)
        self.assertEqual(result['total_cents'],150000)
        self.assertTrue(result['batch_reference'].startswith('IPRB-20260916-'))
        repayments=self.db.all('SELECT * FROM project_funding_repayments ORDER BY id')
        self.assertEqual(len(repayments),2)
        self.assertEqual(len({row['system_reference'] for row in repayments}),2)
        self.assertEqual({row['batch_reference'] for row in repayments},{result['batch_reference']})
        self.assertEqual(self.db.cash_summary()[2],company_before)
        self.assertEqual(self.db.cash_summary(self.grace)[2],grace_before-150000)
        self.assertEqual(self.db.cash_summary(self.oasis)[2],oasis_before+150000)
        self.assertEqual(self.db.repayment_source_available('Cash Receipt',self.grace,receipt),50000)
        self.assertEqual(self.db.interproject_balance(self.grace),(0,0))
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM expenses')['n'],2)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM payments')['n'],2)

    def test_undo_source_tracked_repayment_restores_cash_receipt_availability(self):
        receipt=self.db.execute("""INSERT INTO remittances(project_id,type,amount_cents,txn_date,
            cash_received,system_reference) VALUES(?,'Deposit',100000,'2026-09-15',1,
            'CR-20260915-0001')""",(self.grace,)).lastrowid
        expense=self.expense(self.grace,40000)
        self.db.record_project_payment(expense,40000,'2026-09-14','Cash',self.heads[0],self.oasis,self.allocation)
        loan=self.db.interproject_loans(self.grace)[0]
        repayment=self.db.repay_project_funding(loan['id'],40000,'2026-09-16',self.heads[1],
            source_type='Cash Receipt',source_remittance_id=receipt)
        self.assertEqual(self.db.repayment_source_available('Cash Receipt',self.grace,receipt),60000)
        self.db.undo_project_funding_repayment(repayment,self.heads[1])
        self.assertEqual(self.db.repayment_source_available('Cash Receipt',self.grace,receipt),100000)
        self.assertEqual(self.db.interproject_balance(self.grace),(0,40000))

    def test_repayment_overpayment_is_rejected(self):
        eid=self.expense(self.grace)
        self.db.record_project_payment(eid,100000,'2026-09-14','Cash',self.heads[0],self.oasis,self.allocation)
        with self.assertRaises(ValueError):
            self.db.repay_project_funding(self.db.interproject_loans()[0]['id'],100001,'2026-09-16',self.heads[1])

    def test_voided_expense_removes_active_loan_effects(self):
        eid=self.expense(self.grace)
        self.db.record_project_payment(eid,100000,'2026-09-14','Cash',self.heads[0],self.oasis,self.allocation)
        self.db.execute('UPDATE expenses SET voided=1 WHERE id=?',(eid,))
        self.assertEqual(self.db.interproject_balance(self.oasis),(0,0))
        self.assertEqual(self.db.project_budget(self.oasis)[2],10000000)
        self.assertEqual(len(self.db.interproject_loans(include_inactive=True)),1)

    def test_own_funds_create_no_borrowing(self):
        eid=self.expense(self.oasis)
        self.db.record_project_payment(eid,100000,'2026-09-14','Cash',self.heads[0],self.oasis,self.allocation)
        self.assertEqual(self.db.interproject_loans(),[])

    def test_funding_reassignment_releases_old_project_and_creates_loan(self):
        eid=self.expense(self.grace)
        payment=self.db.record_project_payment(eid,100000,'2026-09-14','Cash',self.heads[1],self.grace,self.allocation)
        self.db.reassign_expense_payment(payment,amount_cents=100000,payment_date='2026-09-14',method='Cash',
            cash_allocation_id=self.allocation,bank_account_id=None,reference='',notes='',correction_reason='Wrong funding project',
            authorized_by_head_id=self.heads[1],funding_project_id=self.oasis)
        self.assertEqual(self.db.project_budget(self.grace)[2],10000000)
        self.assertEqual(self.db.project_budget(self.oasis)[2],9900000)
        self.assertEqual(self.db.interproject_balance(self.grace),(0,100000))
        self.assertEqual(self.db.allocation_spent(self.allocation),100000)

    def test_reassigning_to_own_project_preserves_inactive_loan_history(self):
        eid=self.expense(self.grace)
        payment=self.db.record_project_payment(eid,100000,'2026-09-14','Cash',self.heads[0],self.oasis,self.allocation)
        self.db.reassign_expense_payment(payment,amount_cents=100000,payment_date='2026-09-14',method='Cash',
            cash_allocation_id=self.allocation,bank_account_id=None,reference='',notes='',correction_reason='Own funds',
            authorized_by_head_id=self.heads[1],funding_project_id=self.grace)
        self.assertEqual(self.db.interproject_balance(self.grace),(0,0))
        self.assertEqual(len(self.db.interproject_loans(include_inactive=True)),1)
        self.assertEqual(self.db.project_budget(self.oasis)[2],10000000)

    def test_multi_project_attendance_correction_requires_reopen(self):
        self.two_project_week();self.commit(self.oasis)
        row=self.db.one('SELECT * FROM attendance WHERE project_id=?',(self.grace,))
        with self.assertRaisesRegex(ValueError,'Reopen all'):
            self.db.revise_attendance(row['id'],datetime(2026,9,15,13),datetime(2026,9,15,17),'Wrong times',self.heads[1])

    def test_project_costs_attribute_advance_to_the_work_projects(self):
        self.two_project_week()
        self.db.commit_project_weekly_payrolls(dict(zip(self.projects[:2],self.heads[:2])),'2026-09-14')
        self.assertEqual(self.db.project_cost_budget(self.oasis)[1],300000)
        self.assertEqual(self.db.project_cost_budget(self.grace)[1],200000)

    def test_negative_correction_limits_deduction_without_negative_net(self):
        self.two_project_week()
        self.db.execute("INSERT INTO payroll_adjustments(employee_id,project_id,amount_cents,reason) VALUES(?,?,-190000,'Correction')",(self.employee,self.grace))
        results=self.db.commit_project_weekly_payrolls(dict(zip(self.projects[:2],self.heads[:2])),'2026-09-14')
        self.assertEqual([r['deduction_cents'] for r in results],[90000,10000])
        self.assertTrue(all(r['net_cents']>=0 for r in results))

    def test_partial_reopened_week_cannot_post_duplicate_or_stale_share(self):
        self.two_project_week()
        oasis=self.commit(self.oasis);self.commit(self.grace)
        self.db.reopen_payroll_batch(oasis['id'],'Correction',self.heads[0])
        with self.assertRaises(ValueError):self.commit(self.oasis)
        self.assertEqual(self.db.one("SELECT SUM(amount_cents) n FROM cash_advance_transactions WHERE posted=1 AND txn_type='Salary Deduction'")['n'],40000)

    def test_proportions_are_order_independent(self):
        self.two_project_week()
        self.assertEqual(self.db.weekly_project_deduction(self.employee,self.oasis,'2026-09-14'),60000)
        self.assertEqual(self.db.weekly_project_deduction(self.employee,self.grace,'2026-09-14'),40000)
        grace=self.commit(self.grace);oasis=self.commit(self.oasis)
        self.assertEqual((oasis['deduction_cents'],grace['deduction_cents']),(60000,40000))
        self.assertEqual((oasis['net_cents'],grace['net_cents']),(240000,160000))
        self.assertEqual(self.db.one("SELECT SUM(amount_cents) n FROM cash_advance_transactions WHERE posted=1 AND txn_type='Salary Deduction'")['n'],100000)
        self.assertEqual(self.db.interproject_balance(self.grace),(0,40000))

    def test_reverse_commit_order_same_amounts(self):
        self.two_project_week()
        oasis=self.commit(self.oasis);grace=self.commit(self.grace)
        self.assertEqual((oasis['deduction_cents'],grace['deduction_cents']),(60000,40000))

    def test_three_projects_round_exactly_to_cent(self):
        self.attendance(self.oasis,10000)
        self.attendance(self.grace,10000,'2026-09-15')
        self.attendance(self.third,10000,'2026-09-16')
        self.advance(10001)
        results=self.db.commit_project_weekly_payrolls(dict(zip(self.projects,self.heads)),'2026-09-14')
        self.assertEqual(sum(r['deduction_cents'] for r in results),10001)
        self.assertEqual([r['deduction_cents'] for r in results],[3334,3334,3333])

    def test_weekly_cap_applied_once_not_per_project(self):
        self.attendance(self.oasis,300000);self.attendance(self.grace,200000,'2026-09-15')
        self.advance(100000,50000)
        results=self.db.commit_project_weekly_payrolls(dict(zip(self.projects[:2],self.heads[:2])),'2026-09-14')
        self.assertEqual([r['deduction_cents'] for r in results],[30000,20000])
        self.assertEqual(self.db.one("SELECT SUM(amount_cents) n FROM cash_advance_transactions WHERE posted=0 AND voided=0")['n'],50000)

    def test_deduction_cannot_exceed_combined_earnings(self):
        self.attendance(self.oasis,30000);self.attendance(self.grace,20000,'2026-09-15');self.advance()
        results=self.db.commit_project_weekly_payrolls(dict(zip(self.projects[:2],self.heads[:2])),'2026-09-14')
        self.assertEqual(sum(r['net_cents'] for r in results),0)
        self.assertEqual(sum(r['deduction_cents'] for r in results),50000)

    def test_future_advance_not_deducted(self):
        self.attendance(self.oasis,300000);self.advance(day='2026-09-19')
        self.assertEqual(self.commit(self.oasis)['deduction_cents'],0)

    def test_payroll_commit_allowed_without_project_deposit(self):
        self.db.execute("UPDATE remittances SET voided=1 WHERE project_id=? AND type='Deposit'",(self.grace,))
        self.attendance(self.grace,200000,'2026-09-15')
        result=self.commit(self.grace)
        self.assertEqual(result['net_cents'],200000)
        self.assertEqual(self.db.one('SELECT status FROM expenses WHERE id=?',(result['expense_id'],))['status'],'Unpaid')

    def test_pay_selected_project_payrolls_once_from_shared_dp(self):
        self.two_project_week()
        results=self.db.commit_project_weekly_payrolls(dict(zip(self.projects[:2],self.heads[:2])),'2026-09-14')
        before=self.db.allocation_balance(self.allocation)
        payment=self.db.pay_weekly_project_expenses([r['expense_id'] for r in results],self.allocation,'2026-09-18',self.heads[0])
        self.assertEqual(payment['total_cents'],400000)
        self.assertEqual(payment['remaining_cents'],before-400000)
        self.assertEqual(len(payment['payment_ids']),2)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM payments WHERE cash_allocation_id=?',(self.allocation,))['n'],2)

    def test_group_payment_can_borrow_all_from_one_project(self):
        self.two_project_week()
        results=self.db.commit_project_weekly_payrolls(dict(zip(self.projects[:2],self.heads[:2])),'2026-09-14')
        self.db.execute("UPDATE remittances SET voided=1 WHERE project_id=? AND type='Deposit'",(self.grace,))
        self.db.pay_weekly_project_expenses([r['expense_id'] for r in results],self.allocation,'2026-09-18',self.heads[0],self.oasis)
        self.assertEqual(self.db.interproject_balance(self.grace),(0,200000))
        self.assertEqual(self.db.project_budget(self.grace)[2],0)

    def test_group_commit_rolls_back_if_any_project_fails(self):
        self.two_project_week()
        self.db.execute('UPDATE projects SET contract_value_cents=1 WHERE id=?',(self.grace,))
        with self.assertRaises(ValueError):self.db.commit_project_weekly_payrolls(dict(zip(self.projects[:2],self.heads[:2])),'2026-09-14')
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM payroll_batches')['n'],0)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM payroll_week_plans')['n'],0)
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM cash_advance_transactions WHERE posted=1")['n'],0)

    def test_group_contract_limits_use_gross_project_cost_not_temporary_ca_origin(self):
        self.two_project_week()
        self.db.execute('UPDATE projects SET contract_value_cents=300000 WHERE id=?',(self.oasis,))
        self.db.execute('UPDATE projects SET contract_value_cents=200000 WHERE id=?',(self.grace,))
        results=self.db.commit_project_weekly_payrolls(dict(zip(self.projects[:2],self.heads[:2])),'2026-09-14')
        self.assertEqual(sum(r['net_cents'] for r in results),400000)
        self.assertEqual(self.db.project_cost_budget(self.oasis)[2],0)
        self.assertEqual(self.db.project_cost_budget(self.grace)[2],0)

    def test_changed_attendance_cannot_silently_recalculate_frozen_week(self):
        self.two_project_week();self.commit(self.oasis)
        self.db.execute('UPDATE attendance SET gross_cents=gross_cents+1 WHERE project_id=?',(self.grace,))
        with self.assertRaisesRegex(ValueError,'Attendance changed'):self.commit(self.grace)

    def test_all_project_payrolls_reopen_then_recommit_without_duplicate_recovery(self):
        self.two_project_week()
        results=self.db.commit_project_weekly_payrolls(dict(zip(self.projects[:2],self.heads[:2])),'2026-09-14')
        for result,head in zip(results,self.heads):self.db.reopen_payroll_batch(result['id'],'Correction',head)
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM payroll_week_plans')['n'],0)
        results=self.db.commit_project_weekly_payrolls(dict(zip(self.projects[:2],self.heads[:2])),'2026-09-14')
        self.assertEqual(sum(r['deduction_cents'] for r in results),100000)
        self.assertEqual(self.db.interproject_balance(self.grace),(0,40000))

    def test_unclosed_other_project_attendance_blocks_commit(self):
        self.attendance(self.oasis,300000)
        self.db.execute("INSERT INTO attendance(employee_id,project_id,clock_in,clock_out) VALUES(?,?,'2026-09-15T08:00:00','2026-09-15T17:00:00')",(self.employee,self.grace))
        with self.assertRaisesRegex(ValueError,'every project'):self.commit(self.oasis)

    def test_split_day_is_one_regular_day_with_global_overtime(self):
        ids=self.db.record_batch_project_attendance([
            (self.employee,self.oasis,datetime(2026,9,14,8),datetime(2026,9,14,12)),
            (self.employee,self.grace,datetime(2026,9,14,13),datetime(2026,9,14,18))],self.heads[0])
        rows=self.db.all('SELECT * FROM attendance ORDER BY id')
        self.assertEqual([r['regular_hours'] for r in rows],['4.00','4.00'])
        self.assertEqual([r['overtime_hours'] for r in rows],['0.00','1.00'])
        self.assertEqual(sum(r['gross_cents'] for r in rows),115625)

    def test_edit_staged_segment_recalculates_daily_overtime_across_projects(self):
        ids=self.db.record_batch_project_attendance([
            (self.employee,self.oasis,datetime(2026,9,14,8),datetime(2026,9,14,12)),
            (self.employee,self.grace,datetime(2026,9,14,13),datetime(2026,9,14,18))],self.heads[0])
        self.db.revise_attendance(ids[0],datetime(2026,9,14,9),datetime(2026,9,14,12),'Correct arrival',self.heads[0])
        rows=self.db.all('SELECT * FROM attendance ORDER BY id')
        self.assertEqual([r['overtime_hours'] for r in rows],['0.00','0.00'])
        self.assertEqual(sum(r['gross_cents'] for r in rows),100000)

    def test_external_batch_row_can_borrow_without_borrower_deposit(self):
        self.db.execute("INSERT INTO bank_accounts(bank_name,account_name,account_number) VALUES('Test Bank','Client','123')")
        self.db.execute("UPDATE remittances SET voided=1 WHERE project_id=? AND type='Deposit'",(self.grace,))
        form=BulkExpenseDialog.__new__(BulkExpenseDialog)
        form.db=self.db;form.projects=dict(zip(('Oasis','Grace','Third'),self.projects));form.banks={}
        values=dict(project='Grace',funding_project='Oasis',qty='1',unit_price='1000',item='Tools',dimensions='',
            supplier='',phase=self.db.one('SELECT name FROM phases WHERE project_id=?',(self.grace,))['name'],
            area=self.db.one('SELECT name FROM expense_categories')['name'],status='Paid',payment_method='Cash',
            cash_allocation=self.db.one('SELECT reference FROM cash_allocations WHERE id=?',(self.allocation,))['reference'],
            expense_date='2026-09-14')
        item=form._build_item(values,[])
        self.assertEqual(item['funding_project_id'],self.oasis)
        self.assertEqual(item['project_id'],self.grace)
        self.assertEqual(item['supplier'],'')
        values.update(funding_project='',status='Unpaid')
        old_form_row=form._build_item(values,[])
        self.assertEqual(old_form_row['funding_project_id'],self.grace)

    def test_manual_sources_honor_selected_newer_withdrawal_not_fifo(self):
        newer=self.db.execute("INSERT INTO remittances(project_id,type,amount_cents,txn_date,system_reference) VALUES(?,'Withdrawal',200000,'2026-09-14','WD-MANUAL')",(self.oasis,)).lastrowid
        aid=self.db.create_cash_allocation(project_id=self.oasis,allocation_type='Direct Procurement',amount_cents=200000,
            allocation_date='2026-09-14',issuer_head_id=self.heads[0],receiver_head_id=self.db.one("SELECT id FROM project_heads WHERE project_id=? AND name='Custodian'",(self.oasis,))['id'],supplier='Supplier',
            withdrawal_sources=[(newer,200000)])
        self.assertEqual(self.db.one('SELECT withdrawal_id FROM cash_allocations WHERE id=?',(aid,))['withdrawal_id'],newer)
        self.assertEqual(self.db.one('SELECT source_selection_mode FROM cash_allocations WHERE id=?',(aid,))['source_selection_mode'],'Manual')

    def test_manual_source_totals_must_match_allocation(self):
        with self.assertRaisesRegex(ValueError,'exactly equal'):
            self.db.validate_manual_withdrawal_sources(200000,'2026-09-14',[(self.withdrawal,199999)])

    def test_manual_source_cannot_overdraw_or_select_future_voided_or_duplicate(self):
        with self.assertRaises(ValueError):self.db.validate_manual_withdrawal_sources(20000000,'2026-09-14',[(self.withdrawal,20000000)])
        with self.assertRaises(ValueError):self.db.validate_manual_withdrawal_sources(100000,'2026-09-11',[(self.withdrawal,100000)])
        with self.assertRaises(ValueError):self.db.validate_manual_withdrawal_sources(100000,'2026-09-14',[(self.withdrawal,50000),(self.withdrawal,50000)])
        self.db.execute('UPDATE remittances SET voided=1 WHERE id=?',(self.withdrawal,))
        with self.assertRaises(ValueError):self.db.validate_manual_withdrawal_sources(100000,'2026-09-14',[(self.withdrawal,100000)])

    def test_manual_sources_are_required_and_legacy_cutoff_is_enforced(self):
        with self.assertRaisesRegex(ValueError,'Select withdrawal'):
            self.db.validate_manual_withdrawal_sources(100000,'2026-09-14',None)
        self.db.execute("INSERT INTO app_metadata(key,value) VALUES('cash_allocation_wd_cutoff','2026-09-13')")
        with self.assertRaises(ValueError):self.db.validate_manual_withdrawal_sources(100000,'2026-09-14',[(self.withdrawal,100000)])

    def test_manual_sources_can_split_two_withdrawals(self):
        second=self.db.execute("INSERT INTO remittances(project_id,type,amount_cents,txn_date,system_reference) VALUES(?,'Withdrawal',30000,'2026-09-14','WD-SPLIT')",(self.oasis,)).lastrowid
        result=self.db.validate_manual_withdrawal_sources(100000,'2026-09-14',[(self.withdrawal,70000),(second,30000)])
        self.assertEqual(sum(r[1] for r in result),100000)

    def test_overlapping_segments_rejected_without_partial_insert(self):
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            self.db.record_batch_project_attendance([
                (self.employee,self.oasis,datetime(2026,9,14,8),datetime(2026,9,14,12)),
                (self.employee,self.grace,datetime(2026,9,14,11),datetime(2026,9,14,17))],self.heads[0])
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM attendance')['n'],0)

    def test_existing_attendance_overlap_rejected(self):
        self.attendance(self.oasis,300000)
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            self.db.record_batch_project_attendance([(self.employee,self.grace,datetime(2026,9,14,10),datetime(2026,9,14,15))],self.heads[0])

    def test_add_attendance_after_week_lock_requires_reopening(self):
        self.two_project_week();self.commit(self.oasis)
        with self.assertRaisesRegex(ValueError,'locked'):
            self.db.record_batch_project_attendance([(self.employee,self.grace,datetime(2026,9,16,8),datetime(2026,9,16,12))],self.heads[0])

    def test_backup_is_additive_and_not_repeated(self):
        self.db.close()
        raw=sqlite3.connect(Path(self.folder.name)/'test.db')
        raw.execute('DROP TABLE project_funding_repayments');raw.execute('DROP TABLE project_funding_loans');raw.commit();raw.close()
        self.db=Database(Path(self.folder.name)/'test.db');self.addCleanup(self.db.close)
        self.assertTrue(self.db.project_funding_backup.exists())
        self.assertEqual(self.db.one('SELECT COUNT(*) n FROM projects')['n'],3)
        self.db.close()
        again=Database(Path(self.folder.name)/'test.db');self.addCleanup(again.close)
        self.assertIsNone(again.project_funding_backup)


if __name__=='__main__':unittest.main()
