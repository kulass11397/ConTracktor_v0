# Contractor Project Tracker

A local desktop prototype built entirely with Python's standard library:

- Tkinter desktop interface
- SQLite local database
- No cloud account, browser, server, or third-party package
- Human-readable text export that opens in Windows Notepad

## Run in an IDE

1. Open this folder in PyCharm, VS Code, IDLE, or another Python IDE.
2. Select `app.py`.
3. Run the file with Python 3.11 or newer.

You can also open a terminal in this folder and run:

```powershell
python app.py
```

The application creates `contractor_tracker.db` beside `app.py` the first time
it starts. All project information is stored in that file.

## First test

1. Create a project on the **Projects** tab.
2. Select it in the **Current project** list at the top.
3. Add tasks under the default phases and mark some complete.
4. Add an expense, then record a full or partial payment.
5. Add an employee and use their employee number and PIN to time in and out.
6. Commit closed attendance to Expenses. It will appear as an unpaid payroll
   expense and cannot be committed twice.
7. Add deposits and withdrawals under Remittances.
8. Select **Export TXT** to save a complete report and open it in Notepad.

## Financial behavior

- Expense totals are calculated from quantity × unit price.
- Payments are separate records, supporting unpaid, partially paid and paid
  expenses.
- Financial records are voided/restored instead of silently hard-deleted.
- Payroll is committed once as an unpaid expense.
- Important changes are retained in the exported audit log.
- Currency values are stored as integer cents to avoid floating-point errors.

## Local safety

Use **Backup Database** regularly. Save backups somewhere different from the
working folder, such as an external drive. The backup tool uses SQLite's own
safe backup operation.

This is an evaluation prototype, not certified accounting or statutory payroll
software. Define overtime, break, tax, deduction, and payroll rounding rules
before using it for real wages. Daily-rate pay is currently prorated using:

`hours worked ÷ standard hours × daily rate`
