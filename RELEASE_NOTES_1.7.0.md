# ConTracktor v1.7.0

This cumulative Windows updater preserves the existing client database. No sample or replacement database is included.

## New features

1. **Cross-project expense funding:** batch expenses and payments distinguish the expense project from the funding project. Borrowed payments create linked recoverable balances for the lender and amounts owed by the borrower, without duplicating company-wide expenses.
2. **Inter-project repayments:** record or undo internal project-funds settlement with supporting references and audit history. This does not create an extra supplier payment, expense or bank transaction.
3. **Multi-project batch attendance:** select work projects per employee/segment, record split days, enforce deployment dates and reject overlapping attendance. Regular/overtime hours are shared across the worker's day, using existing pay rules and project rates.
4. **Employee-wide weekly CA deduction:** calculate eligible deductions and weekly caps once, distribute by gross earnings per project using exact-cent rounding, and track recovery through another project's payroll.
5. **Related-project payroll review:** review project gross, deductions, corrections and net payable, then commit selected project payrolls atomically. Each project receives its own unpaid net payroll expense.
6. **Shared payroll payment distribution:** pay selected same-week payroll expenses from one PC/DP allocation while keeping payment amounts and project funding traceable. Partial/multiple-source payments remain available through Payments/Funding Sources.
7. **Updated import forms:** optional Funding Project column/dropdown; older forms default to the expense project. Optional/free-text suppliers are retained.
8. **Manual withdrawal selection:** new PC/DP allocations require WD checkboxes and contribution amounts. Contributions must equal the allocation total. Duplicate, voided, future-dated, depleted and pre-cutoff sources are rejected. The confirmation lists the selected references and amounts; silent FIFO selection is removed from issuance.

## Guarded one-time client WD repair

- Reviews the supplied 17 September backup and corrects **21 PC/DP source trails from 24 August to 16 September**.
- Preserves all withdrawal, allocation, expense, payment, surrender, redeposit and pool-return amounts and statuses.
- Rebuilds source links on related pool returns/redeposits so cash provenance stays consistent.
- Handles the returned 63,050 DP and its replacement 63,250 DP against WD-20260904-0001, using the released 63,050 plus the withdrawal's remaining 200.
- Records the user-confirmed duplicate 37,000 DP attempts against the cancelled WD-20260907-0001 for audit only. Both are fully returned, have no expense payments, and contribute zero net source usage. The actual replacement DP uses WD-20260908-0001.
- Keeps the three July migration allocations and legacy expenses unchanged. Newer records not in the reviewed mapping are preserved, not guessed or overwritten.
- Requires the reviewed references, amounts, dates, withdrawal statuses and old/new links to match. A mismatch safely skips the entire September repair and displays a warning.
- Creates a dedicated SQLite backup and per-allocation old/new-link audit records. A durable marker prevents a second run. Withdrawals before 24 August remain visible but excluded from new allocation sourcing for this repaired client ledger.

## Deployment

Close ConTracktor, export a fresh backup, run **ConTracktor_v1_Update_1.7.0.exe** under the same Windows user, and reopen the existing shortcut. Application and database safety backups are created before installation. The one-time reference repair runs when the updated app first opens, not by replacing the client's database.

Review PC/DP WD references and the dashboard totals after opening. If a repair warning appears, preserve the backup and request review of the newer client backup; do not force the repair. Amounts and financial totals are not changed by the WD repair. Older committed multi-project payrolls are not automatically recalculated; reopen all affected project payrolls before changing a locked shared week.

The executable uses the existing Windows .NET installer and bundled Python runtime without a self-extracting Python packer. It is unsigned: Windows/antivirus warnings cannot be guaranteed absent. SHA256SUMS.txt is provided; download only from this release. Do not disable antivirus protection to install it.
