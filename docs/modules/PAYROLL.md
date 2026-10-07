# Payroll

Implemented reference: active later `PayrollTab` and `Database` in `app.py` at `a329efc`; inspected 2026-10-07. Read [ACCOUNTING_RULES](../ACCOUNTING_RULES.md).

## Purpose

Convert closed work into auditable weekly project payroll obligations while recovering advances once per employee-week.

## Current implementation

`weekly_payroll_summary` provides project staging; `company_weekly_payroll_summary` combines workers across projects. Weeks are Saturday–Friday. Commitment creates a `payroll_batches` row, a net-payable expense and immutable detail snapshots, then links attendance. It does not automatically pay that expense. Group commitment is atomic across selected projects.

Employee-wide `payroll_week_plans` freeze attendance signatures and gross-by-project values. CA shares are proportional to project gross, exact to cents and limited by available pay. Related project payrolls use the same locked plan; commit order must not duplicate recoveries.

## Relevant files/classes/functions

`app.py`: later `PayrollTab`, `ProjectPayrollReview`, `PayrollBatchDetailsDialog`, `WeeklyEmployeeDetailsDialog`. `Database`: `weekly_payroll_summary`, `company_weekly_payroll_summary`, `_preview_week_shares`, `_proportional_cents`, `_lock_employee_week`, `_post_week_project_shares`, `commit_weekly_payroll`, `commit_project_weekly_payrolls`, `_capture_payroll_batch_snapshot`, `reopen_payroll_batch`, `_release_reopened_week_plans`, `pay_weekly_project_expenses`. PDF helpers: `export_payroll_batch_pdf`, `write_payroll_batch_pdf`.

## Database tables and relationships

`payroll_batches` links project, expense and authorizing head, period, gross/deduction/adjustment/net and replacement chain. `payroll_batch_employee_snapshots`/`payroll_batch_attendance_snapshots` preserve detail. `attendance` links to batch/expense. `payroll_week_plans` owns employee-week shares in `payroll_week_ca_shares`; shares link scheduled CA recoveries, project and posting batch. `payroll_adjustments` holds pending/applied corrections. Payments and funding loans belong to payroll expenses or CA-recovery shares.

## Important business rules

- Require completed daily-closed uncommitted attendance. All relevant employee work sites must be closed before freezing the shared week.
- Net = gross - deductions + adjustments. Reject negative employee/project net and commitment beyond the relevant cost limit.
- Committing payroll does not require a project deposit; funding/payment validation is separate.
- Group payment pays actual outstanding net expenses from a selected allocation; unused allocation money remains unused. It does not force allocation and wage totals to match.
- Reopening requires valid authorization/reason and no active repayments on the related expense. It retains snapshots, excludes prior payments, reverses allocation-payment activity, returns deductions/adjustments to pending and detaches attendance. Recommit creates linked replacement history.
- Reopen all affected project payrolls before changing a locked multi-project week; partial reopen cannot silently redistribute already-posted deductions.

## Inputs and outputs

Inputs: week/project selections, closed attendance, rates, CA schedules, pending adjustments, authorization and payment sources. Outputs: staging totals, frozen shares, payroll expense/batch/snapshots, posted deduction records and CA-recovery loans; subsequent payments and optional PDFs. Exports do not post pay.

## Dependencies on other modules

Attendance drives gross; employees/projects drive identity/rates/authorization; CAs drive deductions; expenses/bank/cash operations record actual pay; inter-project funding records borrowed wages and recovered advance cost.

## Workflow example

Finalize/close the week's attendance, review gross minus CA deductions plus adjustments, and commit each affected project payroll. Pay the resulting outstanding net expenses from a real source; commitment alone is not payment.

## Known limitations or technical debt

Earlier `PayrollTab` and `legacy_commit` paths remain; inspect active call sites. Net expenses, gross labor report totals and source cash movements intentionally differ. The system is not a full statutory deductions/tax/benefits engine. Correcting paid single-project attendance can queue a later adjustment; multi-project locks are stricter, so do not assume every correction behaves alike.

## Important invariants and tests

One employee-week deduction plan; exact-cent shares; no future advance deductions; no negative net; no duplicate commitment/payment; committed detail survives reopening; no loan repayment reversal bypass. Tests: `test_company_payroll.py`, `test_project_funding.py`, `test_weekly_grid.py` and payroll snapshot/correction/export tests in `test_app.py`.
