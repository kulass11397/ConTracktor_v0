# ConTracktor v1.2.0

ConTracktor is a local Windows contractor-management system built with Python,
Tkinter, and SQLite. It manages projects, expenses, petty cash, remittances,
attendance, weekly payroll, employee advances, contacts, and calendar events.

## v1.2.0 release highlights

- Repairs the payroll-date defect that allowed a cash advance to be deducted
  from a payroll period ending before the advance was granted.
- Automatically repairs affected historical payroll batches once, preserving
  the advance total and moving invalid deduction postings to the earliest
  eligible committed payroll batch with available salary.
- Creates a timestamped SQLite copy before the v1.2.0 schema/data migration.
- Changes all newly selected payroll weeks to **Saturday through Friday**.
- Adds batch cash-advance entry with one effective date, one funding source,
  employee search and multi-selection, per-employee amount/reason/repayment
  plan, optional weekly limits, running batch totals, one PIN authorization,
  and batch plus individual advance references.
- Prevents salary-deduction plans from using an advance whose grant date falls
  after the selected payroll period.
- Adds project-head editing so authorized users can update a registered head's
  name, position, and PIN across all assigned projects.
- Adds a birthday-friendly calendar with scrollable/typed year, month, and day
  controls in addition to the normal month grid.
- Adds local transaction timestamps and batch references for new employee
  advances.
- Corrects the single/batch cash-advance transaction insert and preserves it as
  an automated regression test.
- Cleans up unreadable encoding artifacts in payroll and cash-advance windows.

## Data safety

The upgrade is additive and does not replace the current SQLite database.

- The installer contains **no SQLite database**.
- Existing installations continue using:
  `%LOCALAPPDATA%\ConTracktor_v1\Data\contractor_tracker.db`
- Before replacing application files, the installer copies the old program to
  `%LOCALAPPDATA%\ConTracktor_v1\AppBackups\Before_v1.2.0_TIMESTAMP\`.
- Before updating an existing client, the installer copies the SQLite database
  and its `-wal`/`-shm` files to
  `%LOCALAPPDATA%\ConTracktor_v1\Data\Backups\Before_v1.2.0_TIMESTAMP\`.
- On first v1.2.0 launch, the app makes another database copy beside the live
  database before running the migration.
- The repair is marked in `app_metadata` and is repeat-safe.

Do not uninstall v1.1.0 before updating. Close ConTracktor and run the v1.2.0
setup over the existing installation.

## Run from Python

Requirements: Python 3.11 or newer with Tkinter.

```powershell
python app.py
```

For a specific test database:

```powershell
$env:CONTRACTOR_DB_PATH = "C:\path\to\contractor_tracker.db"
python app.py
```

## Main modules

- Dashboard with synchronized project selection, contract/deposit/payment
  summaries, remaining commitments, progress, and funding chart.
- Construction phases, milestones, deadlines, and automatic progress.
- Cross-project expenses with partial payments, cash/bank controls, project
  budgets, verification, petty-cash/direct-procurement allocation, searchable
  references, batch entry, and filtered A4 PDF export.
- Shared bank remittances, withdrawals, surrender redeposits, and interbank
  transfers with auditable references.
- Employee profiles, compliance fields, photo storage, attendance kiosk,
  authorized batch attendance, daily closure, Saturday-Friday weekly payroll,
  overtime/lunch rules, and consolidated employee summaries.
- Employee cash advances with recoverable balances, cash/bank/salary-deduction
  recovery, allocation tracking, individual or batch grant workflows, and
  weekly payroll integration.
- Contacts, calendar events, text exports, audit records, and manual SQLite
  backups.

## Financial rules

- Currency is stored as integer cents.
- Payments are separate records, so partial and outstanding balances remain
  visible.
- Cash payments cannot exceed available shared/allocated cash.
- Bank transfers cannot exceed the chosen bank balance.
- Expense commitments cannot exceed the selected project's deposited budget.
- Cash advances remain visible as money out. Salary deductions reduce the
  later payroll expense rather than duplicating the original advance expense.
- Cash advance deductions are eligible only when `advance_date <= payroll
  period end`.
- Cash repayments enter surrendered custody until redeposited; they do not
  silently return to unallocated petty cash.
- Sensitive actions require project-head PIN verification and are audited.

## Validation

The v1.2.0 release includes 23 automated tests and a Tkinter construction smoke
check. The supplied client database was tested on a copy with:

- SQLite `quick_check`: `ok`
- Projects preserved: 1
- Employees preserved: 22
- Cash advances preserved: 21
- Invalid future-dated deduction postings after repair: 0

The observed client batches were repaired to:

- `PAYW-20260803-0001`: gross 10,900.00; deductions 600.00; net 10,300.00
- `PAYW-20260810-0001`: gross 57,550.00; deductions 23,900.00; net 33,650.00

This remains local business software, not certified accounting, tax, or
statutory payroll software. Protect the Windows account, enable disk encryption
where available, and keep off-device backups.
