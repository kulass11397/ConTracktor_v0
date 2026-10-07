# Inter-project funding

Implemented reference: `app.py` at `a329efc`; inspected 2026-10-07. Read [EXPENSES](EXPENSES.md), [CASH_OPERATIONS](CASH_OPERATIONS.md) and [ACCOUNTING_RULES](../ACCOUNTING_RULES.md).

## Purpose

Separate construction cost ownership from financing, and track what borrowing projects still owe to funding projects.

## Current implementation

`record_project_payment` creates/synchronizes an ordinary Expense funding loan when payment funding differs from the expense project. A CA recovery loan is created when a payroll deduction attributes an advance to a different work project. `interproject_loans` derives activity/outstanding from linked records and active repayments; inactive history is retained.

The Inter-project Funding view exposes lender/borrower entries, outstanding totals, selected loan repayments and history. Batch repayment selects multiple loans with the same borrowing project and the same funding project, pays their full outstanding amounts, and uses one available source. Repayment is a settlement/ownership event, not another supplier payment.

## Relevant files/classes/functions

`Database`: `_sync_project_funding_loan`, `_post_week_project_shares`, `interproject_loans`, `interproject_balance`, `_funding_cash_adjustment`, `_project_cash_repayment_adjustment`, `project_funding_repayment_sources`, `repayment_source_available`, `repay_project_funding`, `repay_project_funding_batch`, `undo_project_funding_repayment`, `assert_funding_reversal_allowed`. `ExpensesTab`: funding page, loan details, `record_project_repayment`, `undo_project_repayment`, funding/settlement filters and lender derived rows.

## Database tables and relationships

`project_funding_loans` links distinct lender/borrower projects to the single expense and either payment or CA share/payroll batch. `project_funding_repayments` references a loan, amount/date, authorization, source type/remittance/bank and batch/system references. Payments/expense/batch eligibility determines whether the loan remains financially active. Receipt ownership accounts are derived using repayments tied to the original remittance, not another table of deposits.

## Important business rules

- Loans reflect amounts actually paid/funded; an unpaid expense alone does not create ordinary paid borrowing.
- Outstanding = principal minus nonvoid repayments for active loans, bounded at zero. Supplier-paid and lender-settled are independent.
- Positive repayment cannot exceed outstanding, precede borrowing, exceed borrowing-project funds or exceed selected source availability.
- Sources include Cash Receipt, Unallocated Cash on Hand, Bank Account and retained Legacy / Unspecified compatibility. The UI uses explicit available sources; a legacy unlinked record is not proof of physical source provenance.
- Cash-receipt repayment reassigns borrower cash ownership to lender while total company cash is unchanged. It does not refill the original DP/PC account.
- Bank-source repayment is not an automatic bank-to-bank transfer. Physical bank movement, if applicable, is recorded separately and referenced, without another expense/deposit.
- Changing/reversing funding or payroll with active repayments is blocked until repayment is undone. Undo checks lender funding/receipt cash availability and preserves reversal history.

## Inputs and outputs

Inputs: loan(s), amount/date, supporting reference, source, notes and authorizing head. Outputs: repayment rows, audit entries, reduced outstanding balances, funding adjustments and—for receipt cash—derived lender-owned allocable account amounts. Batch posting is atomic and shares a batch reference.

## Dependencies on other modules

Expense payments and CA attribution create debts. Projects supply fund balances and identities. Cash operations expose owner-account availability. Bank module supplies balances/movements. Reporting shows debt separately from supplier outstanding/cost.

## Workflow example

Project A pays a Project B supplier, creating B's debt to A. Record repayment from B's placed cash receipt. The original receipt then exposes lender-owned reimbursed cash; A's old DP is not refilled. Select a single lender/borrower pair for batch repayment.

## Known limitations or technical debt

This is not a dedicated loan/general-ledger engine. Ordinary and CA-recovery activity derive from different linkage predicates. Legacy records may lack source details. Source fields added by upgrade are not all declared foreign keys. Undo checks aggregate lender funding/cash availability, not a complete source-specific dependency ledger; do not claim that every downstream use is automatically traced. Batch settlement is restricted to one lender/borrower pair, not arbitrary funding projects in one batch. Old workflow notes describe less detailed repayment forms than the current implementation.

## Important invariants and tests

One cost, multiple linked views; borrower/lender adjustments conserve company totals; no repayment double-expense; no creation of another receipt; no automatic resurrection of original custody; exact atomic batch settlement and safe undo. Coverage: `test_project_funding.py`, company-payroll and receipt/recovery cases in `test_app.py`.
