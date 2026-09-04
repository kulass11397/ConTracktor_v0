# ConTracktor v1.6.7

## Reopen committed payroll safely

- Adds **Reopen for Correction** under Payroll > Committed Weekly Payrolls.
- Requires a correction reason and project-head authorization.
- Reverses every active payment attached to the payroll expense and restores
  the corresponding Petty Cash, Direct Procurement, or bank balance.
- Returns the payroll's closed attendance to the original Saturday-Friday
  weekly staging period.
- Returns salary-deduction recoveries and applied payroll adjustments to
  pending so they are calculated exactly once when recommitted.
- Keeps the original payroll totals and daily attendance as an audit snapshot,
  even after the live attendance is corrected.
- Marks the original expense as **Payroll Reopened**, excluding it from active
  expense totals without deleting it.
- Recommitting creates a new payroll batch and expense that identify the
  original reference they replace. The old batch becomes **Superseded**.

## Expense-ledger protection

- Payroll expenses can no longer be voided independently from the payroll
  workflow. The app directs the user to Reopen for Correction instead.
- Reopened and superseded payroll expenses cannot be restored on their own,
  preventing duplicate active payroll expenses.

## Preserved records and compatibility

- Existing client data remains in
  `%LOCALAPPDATA%\ConTracktor_v1\Data\contractor_tracker.db`.
- The updater contains no database, WAL, or SHM file.
- It creates timestamped application and database backups before installation.
- Existing committed payrolls receive additive audit snapshots when the new
  version first opens.
- All previous v1.6.6 payment-source, payroll PDF, cash-advance, remittance,
  inventory, employee, and validation improvements remain included.

## Verification

- Python compilation passed.
- All 44 automated tests passed.
- Migration was tested against the supplied client backup; SQLite quick-check
  returned `ok` and 31 employee plus 160 daily payroll snapshots were retained.

