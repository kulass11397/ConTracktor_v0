# Cash advances

Implemented reference: `app.py` at `a329efc`; inspected 2026-10-07. Read [PAYROLL](PAYROLL.md), [CASH_OPERATIONS](CASH_OPERATIONS.md) and [ACCOUNTING_RULES](../ACCOUNTING_RULES.md).

## Purpose

Track money advanced to employees, the project/source supplying it, scheduled or physical recoveries and attribution when wages belong to another work project.

## Current implementation

The active payroll page provides single and company-wide batch grants, persistent drafts, recovery recording, void/correction and export. Batch grants choose an explicit cash funding project; employee home/deployment does not determine the funding project or roster eligibility. Each committed grant has its own advance and linked expense/payment, with a batch header when applicable.

Repayment plans distinguish Salary Deduction, Cash Repayment, Bank Repayment and manual recovery behavior. A Salary Deduction schedule is pending (`posted=0`) until payroll applies it. `salary_deduction_plan` selects eligible schedules FIFO, bounded by employee pay and per-advance weekly cap. Partial posting keeps a pending remainder. A preview does not post recovery.

## Relevant files/classes/functions

`app.py`: `CashAdvanceGrantDialog`, `CashAdvanceBatchDialog`, `CashAdvanceRecoveryDialog`, `CashAdvanceExportDialog`, active `PayrollTab.grant_cash_advance/grant_cash_advance_batch/record_recovery`. `Database`: `salary_deduction_plan`, `post_salary_deduction_plan`, `reduce_pending_salary_schedule`, `void_cash_advance`, `void_cash_advance_recovery`, `_post_week_project_shares`, `payroll_ca_attributions`. Reports: `export_cash_advance_pdf`/`write_cash_advance_pdf`.

## Database tables and relationships

`cash_advances` links employee, funding project, expense, bank/allocation, batch, original amount and repayment settings. `cash_advance_batches` stores funding/authorization and totals. `cash_advance_transactions` stores issuance/recovery/schedule details with posted/voided flags and optional payroll link. `payroll_week_ca_shares` tracks project attribution. `project_funding_loans` can link a CA recovery to its work project. `cash_repayment_surrenders` tracks physically received cash awaiting bank deposit; it does not automatically refill the original allocation.

## Important business rules

- Grant consumes a validated real funding source; draft saves do not consume it.
- Future-dated advances are ineligible for earlier payroll. Caps apply once per employee-week/advance, not anew for each work project.
- Scheduled deductions must not exceed available wages after applicable negative corrections. Proportional project amounts preserve the exact original deduction total.
- Physical repayment and salary deduction are not interchangeable. Cash/bank recoveries affect custody; salary recovery changes payable wages and cost attribution.
- Void/recovery reversal checks dependent payroll/redeposit states, restores balances and keeps audit records. Undo required dependent operations first.

## Inputs and outputs

Inputs: employee(s), explicit funding project, date/amount/reason, allocation/bank, repayment plan/cap and authorization. Outputs: draft payload or advance batch/individual expense/payment records, pending/posted recovery rows, outstanding advance views, surrender records where applicable, attribution loans and PDFs.

## Dependencies on other modules

Employee IDs survive site changes. Payroll consumes scheduled deductions. Projects own initial funding and work costs; cash/bank modules validate custody; inter-project funding records recovered labor due to the original funding project.

## Workflow example

Grant an employee an advance funded by Project A and select Salary Deduction. When wages are earned at Project B, the employee-week deduction recovers the advance and creates the linked attribution debt; record B's repayment to A separately.

## Known limitations or technical debt

Advance balances and expense/report recoveries use different filtered aggregates. Posted recovery is not proof of inter-project repayment. Some historical deduction repair logic remains. Grants/recoveries use direct UI SQL as well as database methods, so changing one helper may not update every posting path.

## Important invariants and tests

No duplicate issue/recovery, no future or excessive deduction, no replay of voided/posting history, no automatic restoration of old DP custody from a project reimbursement. Construction reporting must not count recovered advances twice. Tests: batch/void/recovery cases in `test_app.py`, `test_company_batches.py`, `test_company_payroll.py`, and attribution/cap/reopen cases in `test_project_funding.py`.
