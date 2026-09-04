# ConTracktor v1.6.3

ConTracktor is a local Windows contractor-management system built with Python,
Tkinter, and SQLite. It manages projects, expenses, petty cash, remittances,
attendance, weekly payroll, employee advances, inventory, contacts, and events.

## v1.6.3 release highlights

- Separates the physical cash amount from an optional bank withdrawal fee.
- Keeps only physical cash in the shared cash pool and PC/DP allocations.
- Automatically records the fee as a linked, bank-paid `BANK FEES` expense,
  so cash plus fee reduces the bank exactly once.
- Supports audited corrections of overstated withdrawals and linked unused
  allocation principal after any active surrender/redeposit is voided.
- Adds auditable void/restore controls for petty-cash surrenders and cash
  redeposits.
- Adds searchable weekly-payroll PDF exports with employee summaries and daily
  attendance details.
- Includes the clean interface, global mouse-wheel routing, multi-project
  employees, employee archive/reactivation, editable closed attendance,
  project inventory, project completion records, batch verification, flexible
  suppliers, and prior payroll/cash-advance accounting repairs.

See [RELEASE_NOTES_1.6.3.md](RELEASE_NOTES_1.6.3.md) for the accounting details
and [UPDATE_GUIDE_1.6.3.txt](UPDATE_GUIDE_1.6.3.txt) for client instructions.

## Data safety

The update is additive and does not replace the current SQLite database.

- The installer contains no SQLite database.
- Existing installations continue using
  `%LOCALAPPDATA%\ConTracktor_v1\Data\contractor_tracker.db`.
- Before replacing application files, the installer copies the old program to
  `%LOCALAPPDATA%\ConTracktor_v1\AppBackups\Before_v1.6.3_TIMESTAMP\`.
- Before updating an existing client, it copies the database and any WAL/SHM
  sidecars to
  `%LOCALAPPDATA%\ConTracktor_v1\Data\Backups\Before_v1.6.3_TIMESTAMP\`.
- Required schema additions are applied in place when the updated app opens.

Do not uninstall the existing app before updating. Close ConTracktor and run
the v1.6.3 updater over the existing installation.

## Run from Python

Requirements: Python 3.11 or newer with Tkinter.

```powershell
python app.py
```

The optional clean interface uses the same records and workflows:

```powershell
python app_clean.py
```

For a specific test database:

```powershell
$env:CONTRACTOR_DB_PATH = "C:\path\to\contractor_tracker.db"
python app.py
```

## Main modules

- Dashboard with synchronized project selection, contract/deposit/payment
  summaries, remaining commitments, progress, and funding charts.
- Construction phases, milestones, deadlines, and completed-project archives.
- Cross-project expenses with partial payments, cash/bank controls, project
  budgets, verification, PC/DP allocation, batch entry, imports, and PDF export.
- Shared bank remittances, withdrawal fees, surrenders, redeposits, and
  interbank transfers with auditable references.
- Employee profiles, project assignments, archive/reactivation, attendance,
  Saturday-Friday weekly payroll, payroll PDF export, and attendance revision.
- Employee cash advances with cash/bank/salary-deduction recovery, allocation
  tracking, individual and batch workflows, and weekly payroll integration.
- Consumable and non-consumable project inventory with borrowing, returns,
  restocking, employee accountability, usage, and audit history.
- Contacts, calendar events, exports, audit records, and manual backups.

## Financial rules

- Currency is stored as integer cents.
- Payments are separate records, so partial and outstanding balances remain
  visible.
- Cash payments cannot exceed available shared/allocated cash.
- Bank transfers cannot exceed the chosen bank balance.
- Expense commitments cannot exceed the selected project's deposited budget.
- Withdrawal cash and bank fees are separate: only cash enters allocations;
  the fee is a linked bank-paid expense.
- Cash advances remain visible as money out. Salary deductions reduce the
  later payroll expense rather than duplicating the original advance expense.
- Cash advance deductions are eligible only when the advance date is on or
  before the payroll period end.
- Cash repayments enter surrendered custody until redeposited; they do not
  silently return to unallocated petty cash.
- Sensitive corrections remain audited.

## Validation

The v1.6.3 source passes 39 automated tests. The record-preserving updater was
also tested against an existing SQLite database: the live database remained
byte-for-byte unchanged, the timestamped safety backup matched it, and the
installer payload contained no database files.

This remains local business software, not certified accounting, tax, or
statutory payroll software. Protect the Windows account, enable disk encryption,
and keep off-device backups.
