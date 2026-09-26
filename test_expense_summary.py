import unittest
from pathlib import Path
from unittest.mock import patch
from app import (build_expense_billing_context,build_expense_client_summary,
                 build_uncommitted_payroll_context,write_expense_ledger_pdf)
import test_project_funding as fixtures


class ExpenseSummaryTests(unittest.TestCase):
    setUp=fixtures.ProjectFundingTests.setUp
    expense=fixtures.ProjectFundingTests.expense
    attendance=fixtures.ProjectFundingTests.attendance
    advance=fixtures.ProjectFundingTests.advance
    commit=fixtures.ProjectFundingTests.commit

    def rows(self):
        return self.db.all("""SELECT e.*,COALESCE(ph.name,'') phase,
            COALESCE((SELECT SUM(p.amount_cents) FROM payments p WHERE p.expense_id=e.id AND p.accounting_excluded=0),0) payment_total,
            COALESCE((SELECT SUM(t.amount_cents) FROM cash_advances ca JOIN cash_advance_transactions t ON t.advance_id=ca.id
                WHERE ca.expense_id=e.id AND ca.voided=0 AND t.voided=0 AND t.posted=1
                AND t.txn_type IN ('Cash Repayment','Bank Repayment','Repayment')),0) recovery_total,
            COALESCE((SELECT ca.id FROM cash_advances ca WHERE ca.expense_id=e.id AND ca.voided=0 LIMIT 1),0) cash_advance_id
            FROM expenses e LEFT JOIN phases ph ON ph.id=e.phase_id ORDER BY e.id""")

    def context(self,rows=None,**kwargs):
        return build_expense_client_summary(self.db,self.rows() if rows is None else rows,[self.oasis],**kwargs)

    def test_duplicate_rows_voids_and_split_payments_not_double_counted(self):
        eid=self.expense(self.oasis,100000)
        void=self.expense(self.oasis,900000)
        self.db.execute('UPDATE expenses SET voided=1 WHERE id=?',(void,))
        self.db.execute("INSERT INTO payments(expense_id,amount_cents,payment_date,method) VALUES(?,20000,'2026-09-15','Cash')",(eid,))
        self.db.execute("INSERT INTO payments(expense_id,amount_cents,payment_date,method) VALUES(?,30000,'2026-09-16','Bank Transfer')",(eid,))
        self.db.execute("INSERT INTO payments(expense_id,amount_cents,payment_date,method,accounting_excluded) VALUES(?,90000,'2026-09-16','Cash',1)",(eid,))
        rows=self.rows();context=self.context(rows+rows)
        metrics=dict(context['metrics'])
        self.assertEqual(context['construction_cents'],100000)
        self.assertEqual(metrics['Payments recorded - selected expenses'],50000)
        self.assertEqual(metrics['Outstanding payments - selected expenses'],50000)
        self.assertEqual(sum(context['sources'].values()),50000)
        self.assertIn('Void entries excluded: 1',context['counts'])

    def test_gross_payroll_addback_and_advance_separation(self):
        self.attendance(self.oasis,100000)
        self.advance(40000)
        self.commit(self.oasis)
        context=self.context()
        metrics=dict(context['metrics'])
        self.assertEqual(metrics['Labor - gross committed payroll / recorded labor'],100000)
        self.assertEqual(metrics['Employee advances issued - separate from construction cost'],40000)
        self.assertEqual(metrics['Payroll deductions already advanced - included in gross labor'],40000)
        self.assertEqual(context['construction_cents'],100000)
        self.assertEqual(metrics['Selected-period ledger total - after cash recoveries'],100000)

    def test_cash_repayment_reduces_ledger_not_construction_materials(self):
        self.expense(self.oasis,100000)
        aid=self.advance(40000)
        self.db.execute("INSERT INTO cash_advance_transactions(advance_id,txn_type,amount_cents,txn_date,method,posted) VALUES(?,'Cash Repayment',10000,'2026-09-16','Cash',1)",(aid,))
        context=self.context()
        self.assertEqual(context['construction_cents'],100000)
        self.assertEqual(dict(context['metrics'])['Selected-period ledger total - after cash recoveries'],130000)
        self.assertEqual(dict(context['metrics'])['Cash / bank recoveries - selected expenses'],10000)

    def test_running_totals_ignore_row_filters_but_honor_projects_and_cutoff(self):
        early=self.expense(self.oasis,100000)
        selected=self.expense(self.oasis,200000)
        late=self.expense(self.oasis,300000)
        self.expense(self.grace,400000)
        self.db.execute("UPDATE expenses SET expense_date='2026-09-10' WHERE id=?",(early,))
        self.db.execute("UPDATE expenses SET expense_date='2026-09-15' WHERE id=?",(selected,))
        self.db.execute("UPDATE expenses SET expense_date='2026-09-20' WHERE id=?",(late,))
        rows=[r for r in self.rows() if r['id']==selected]
        context=self.context(rows,date_from='2026-09-15',date_to='2026-09-18')
        self.assertEqual(context['construction_cents'],200000)
        self.assertEqual(context['funding'][0][1],300000)
        self.assertEqual(context['period'],'09/15/2026 to 09/18/2026')

    def test_phase_category_area_and_site_each_equal_same_cost_total(self):
        one=self.expense(self.oasis,100000)
        two=self.expense(self.oasis,200000)
        self.db.execute("UPDATE expenses SET trade='Electrical Works',area='Ground Floor' WHERE id=?",(one,))
        self.db.execute("UPDATE expenses SET trade='Bank Charges',area='BANK FEES' WHERE id=?",(two,))
        context=self.context()
        for key in ('phases','categories','areas','sites'):
            self.assertEqual(sum(context[key].values()),context['construction_cents'])
        self.assertEqual(dict(context['metrics'])['Bank fees / charges'],200000)
        self.assertIn('Unassigned phase',context['phases'])

    def test_report_generation_is_read_only_and_preserves_ids(self):
        self.expense(self.oasis,100000)
        before=self.db.conn.total_changes
        context=self.context(metadata=dict(title='Manabat Residence - Two Storey Building',address='Alapan 1A, Imus City, Cavite',period_label='1st week',signatures='Kent Miguel Fajardo, Ar. Randy Fauni, Alijah Tapayan'))
        self.assertEqual(before,self.db.conn.total_changes)
        self.assertEqual(context['signatures'],['Kent Miguel Fajardo','Ar. Randy Fauni','Alijah Tapayan'])
        self.assertEqual(context['period_label'],'1st week')

    def test_summary_only_has_breakdowns_and_signatures_but_no_detail_table(self):
        self.expense(self.oasis,100000)
        context=self.context(metadata=dict(title='Client project',signatures='Kent Miguel Fajardo, Ar. Randy Fauni, Alijah Tapayan'))
        path=Path(self.folder.name)/'summary.pdf'
        write_expense_ledger_pdf(path,[('Project','Oasis')],[],[],client_summary=context,include_details=False)
        payload=path.read_bytes()
        self.assertIn(b'FINANCIAL SUMMARY',payload)
        self.assertIn(b'PHASE BREAKDOWN',payload)
        self.assertIn(b'CATEGORY / TRADE BREAKDOWN',payload)
        self.assertIn(b'Montarra Solutions | Project Financial Summary',payload)
        self.assertNotIn(b'TOTALS BY STATUS',payload)
        self.assertIn(b'Ar. Randy Fauni',payload)
        self.assertTrue(payload.rstrip().endswith(b'%%EOF'))

    def test_summary_pagination_with_many_long_categories(self):
        self.expense(self.oasis,100000)
        context=self.context(metadata=dict(signatures=''))
        context['categories']={f'Construction category {i} - long description with additional client context':1000 for i in range(120)}
        context['construction_cents']=120000
        path=Path(self.folder.name)/'many.pdf'
        write_expense_ledger_pdf(path,[],[],[],client_summary=context,include_details=False)
        payload=path.read_bytes()
        self.assertIn(b'category 119',payload)
        self.assertGreater(payload.count(b'/Type /Page '),5)

    def test_invalid_dates_and_too_many_signers_rejected(self):
        self.expense(self.oasis)
        with self.assertRaises(ValueError):self.context(date_from='2026-09-18',date_to='2026-09-15')
        with self.assertRaises(ValueError):self.context(metadata=dict(signatures=', '.join(str(i) for i in range(10))))
        with self.assertRaises(ValueError):write_expense_ledger_pdf(Path(self.folder.name)/'invalid.pdf',[],[],[],include_details=False)

    def test_uncommitted_attendance_is_included_once_and_committed_payroll_is_not_duplicated(self):
        self.attendance(self.oasis,100000,'2026-09-14')
        staged=build_uncommitted_payroll_context(
            self.db,[self.oasis],'2026-09-14','2026-09-20')
        self.assertEqual(staged['gross_cents'],100000)
        self.assertEqual(staged['attendance_entries'],1)
        self.assertEqual(staged['employees'][0]['employee_name'],'Worker')
        self.assertEqual(staged['daily'][0]['work_date'],'2026-09-14')
        before=self.context([],date_from='2026-09-14',date_to='2026-09-20')
        self.assertEqual(before['construction_cents'],100000)
        self.assertIn('Uncommitted attendance included: 1',before['counts'])
        self.commit(self.oasis)
        after=self.context(date_from='2026-09-14',date_to='2026-09-20')
        self.assertEqual(after['staged_payroll']['attendance_entries'],0)
        self.assertEqual(dict(after['metrics'])['Labor - gross committed payroll / recorded labor'],100000)
        self.assertEqual(after['construction_cents'],100000)

    def test_billing_uses_only_outstanding_linked_project_funding(self):
        expense_id=self.expense(self.grace,200000)
        self.db.record_project_payment(expense_id,150000,'2026-09-14','Cash',
            self.heads[0],self.oasis,self.allocation)
        rows=[row for row in self.rows() if row['id']==expense_id]
        context=build_expense_client_summary(
            self.db,rows,[self.grace],metadata={'include_staged_payroll':'No'})
        billing=build_expense_billing_context(
            self.db,rows,context,'15','Grace Manabat','Kent Miguel Fajardo',
            'Outstanding inter-project funding','')
        self.assertEqual(billing['reimbursement_cents'],150000)
        self.assertEqual(billing['fee_cents'],30000)
        self.assertEqual(billing['amount_due_cents'],180000)
        self.assertEqual(len(billing['reimbursement']),1)

    def test_combined_billing_pdf_contains_one_amount_due_page(self):
        self.expense(self.oasis,100000)
        rows=self.rows()
        context=self.context(rows,metadata=dict(
            title='Manabat Residences - Two Storey Building',
            address='Alapan 1A, Imus City, Cavite',include_staged_payroll='No'))
        context['billing']=build_expense_billing_context(
            self.db,rows,context,'15','Grace Manabat','Kent Miguel Fajardo',
            'Manual amount','2000')
        path=Path(self.folder.name)/'combined-billing.pdf'
        write_expense_ledger_pdf(path,[],[],[],client_summary=context,include_details=False)
        payload=path.read_bytes()
        self.assertIn(b'BILLING STATEMENT - REIMBURSEMENT AND MANAGEMENT FEE',payload)
        self.assertIn(b'CONSTRUCTION EXPENSE REIMBURSEMENT SUBTOTAL',payload)
        self.assertIn(b'TOTAL AMOUNT DUE',payload)
        self.assertNotIn(b'CONSTRUCTION EXPENSES BILLING',payload)
        self.assertNotIn(b'MANAGEMENT FEE BILLING',payload)


if __name__=='__main__':unittest.main()
