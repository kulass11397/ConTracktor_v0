# ConTracktor v0

ConTracktor is a local contractor project-management prototype built with Python, Tkinter, and SQLite. It follows the supplied dark-sidebar dashboard design and requires no server, browser, cloud account, or third-party Python package.

## Requirements

- Windows, macOS, or Linux
- Python 3.11 or newer with Tkinter

## Run it

In an IDE, open this folder and run `app.py`.

From PowerShell or a terminal:

```powershell
python app.py
```

On Windows, you can also double-click `run_app.bat`.

The app creates `contractor_tracker.db` beside `app.py` on first launch. That single SQLite file contains the local project data.

## Recommended first walkthrough

1. Choose **New Project** on the Dashboard.
2. Enter the project details and add one or more project heads. Each head creates a private PIN.
3. Add milestones and tasks under the default, removable construction phases.
4. Add an expense. Review the confirmation and have a project head authorize it with their PIN.
5. Add employees, then use the attendance kiosk to time in and out. Choose **Expand Kiosk** for a dedicated full-screen employee station; press Escape to leave it.
6. Commit completed attendance to the expense ledger. A project-head PIN is required and the payroll batch appears as an unpaid expense.
7. Record client deposits and construction withdrawals. These also require project-head authorization.
8. Add contacts and calendar reminders, meetings, schedules, or deadlines.
9. Open **Tools** to export a project report to a UTF-8 text file or create a safe SQLite backup.

## Included modules

- Dashboard with financial, progress, and upcoming-event summaries
- Construction phases, milestones, deadlines, completion tracking, and automatic progress
- Detailed expense ledger, payments, status, filtering, void/restore, and authorizer history
- Contacts directory
- Employee roster, PIN attendance, hourly/daily pay calculation, and payroll-to-expense commit
- Client deposit and contractor withdrawal ledger with funding progress
- Month calendar and upcoming-event list
- Multiple project heads with salted, one-way hashed PINs
- Text export, audit log, and SQLite backup

## Financial and security behavior

- Currency is stored as integer cents to avoid floating-point rounding errors.
- Payments are separate records, allowing unpaid, partial, and paid expense states.
- Expenses and remittances are voided/restored instead of silently deleted.
- Payroll attendance can be committed only once.
- Project-head and employee PINs are salted and hashed; the original PIN is not stored.
- Expense creation, remittance creation, and payroll commit require a project-head PIN and record the authorizer.

This remains a local prototype. Anyone who can copy the database file can access its business data, although they cannot read the original PINs from it. Protect the Windows account, enable full-disk encryption such as BitLocker where available, and save regular backups to a separate drive. A server is unnecessary for one trusted computer, but authentication, encrypted transport, access roles, and managed backups should be designed before multi-computer or internet use.

This is not certified accounting or statutory payroll software. Confirm overtime, break, tax, deduction, and rounding rules before using it for real wages. Daily-rate pay is prorated as `hours worked / standard hours * daily rate`.
