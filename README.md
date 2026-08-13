# ConTracktor v1

Current release: **v1.1.0**

## v1.1.0 accounting and custody update

- Weekly payroll expenses are committed at net payable: gross salary minus posted salary deductions.
- Salary deductions settle employee advances but are not counted again as payroll payments or petty-cash movements.
- Employee cash advances remain visible as money-out expenses for a complete audit trail.
- Physical cash repayments are locked as surrendered cash instead of returning to spendable unallocated cash.
- Every cash repayment receives an `SR` surrender reference and appears in a dedicated repayment-surrender ledger.
- **Deposit All Surrendered** includes both returned allocation balances and employee cash repayments.
- The cash-allocation ledger distinguishes Money Out, Repayment Surrendered, Net Expense, and Spendable Remaining.
- Existing payroll, payment, cash-advance, and repayment records are migrated additively without deleting their history.

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

1. Choose **Add Project Head** on the Dashboard and register the people who may head projects.
2. Choose **New Project**, enter its details and project address, and assign one or more registered heads from the dropdown.
3. Add milestones and tasks under the default, removable construction phases.
4. Enroll at least one shared bank account in **Remittances**, then record project deposits.
5. Add one or more expense items as a batch. Each selected project requires one project-head authorization.
6. Add employees with their birthday, compliance checklist, and optional embedded 1x1 picture, then use the attendance kiosk to time in and out. Choose **Expand Kiosk** for a dedicated full-screen employee station; press Escape to leave it.
7. Use **Close Daily Attendance** after each work day. Review the Monday-Sunday accumulation in **Weekly Payroll**, then use **Commit This Week to Expenses** at week end. Both protected steps require a project-head PIN; only the weekly commit creates an unpaid expense.
8. Use **Cash Advances** to grant an employee advance, then record each cash repayment, bank repayment, or salary deduction without deleting the original expense.
9. Add contacts and calendar reminders, meetings, schedules, or deadlines.
10. Open **Tools** to export project text reports, filtered expense PDFs, or create a safe SQLite backup.

For the supplied Project Oasis test roster, run `seed_project_oasis_employees.py` or double-click `seed_project_oasis_employees.bat`. The seeder is safe to run repeatedly and will not duplicate its ten synthetic employees. Their kiosk PIN is **0000**.

## Included modules

- Dashboard with one synchronized **All Projects / specific project** selector and totals for contract value, deposited contract value, payments, outstanding commitments, and progress
- Dashboard reconciliation explicitly confirms that recorded payments plus outstanding balances equal all active expense commitments
- Responsive dashboard metric cards plus a nested funding chart: contract funding on the outer ring, deposited-fund use on the middle ring, outstanding coverage on the inner ring, and construction progress in the center
- Context-aware **Edit Project** and **Project Heads** controls that are enabled only when one project is selected
- Construction phases, milestones, deadlines, completion tracking, and automatic progress
- Cross-project expense ledger with project, simplified checkbox status, checkbox MOP, area, supplier, date, and text filters
- **Pending-Partial** finds expenses with a recorded payment and a remaining balance; **Pending-Outstanding** finds every active expense that still has a balance due
- The Payments Recorded summary card also displays the filtered outstanding-payment total directly beneath it
- Expense summary cards cover filtered expenses, filtered payments and outstanding balances, shared cash-on-hand, deposited project funds, committed-budget remaining, total contracts, and collectible contracts
- Clicking an expense's **Payment Dates** cell opens its full payment history with date, amount, MOP, authorizing head, reference, and notes
- Double-clicking an expense opens a two-column detail card with an **Edit Expense** route to the existing all-head approval workflow
- Multi-item, single-project expense batches with per-item Paid, Partially Paid, or Unpaid state
- Partially Paid items require an initial payment amount and immediately create a Cash or Bank Transfer payment record
- Simplified required bulk fields, a calendar picker, a permanently visible **Commit Batch to Expense Ledger** button, and Paid/Outstanding totals broken down by cash and bank transfer
- Live shared cash-on-hand and enrolled-bank after-batch previews, with commit-time cash, per-bank, and project-budget validation
- Expense-date range filtering with today as the default, calendar pickers for both boundaries, and an **All Dates** shortcut
- Checkbox status filtering supports any combination of Paid, Partially Paid, Unpaid, and Void records
- Readable color-coded expense states: Paid in green, partially paid in orange, unpaid in red, and voided rows in gray
- Expense ledger MOP values show the actual recorded payment method, including Cash, Bank Transfer, mixed methods, or Not Paid
- A live reconciliation line explains how deposits split between all active expense commitments and remaining budget, including amounts excluded by current filters
- Searchable supplier selection that can create supplier contacts from the expense form
- Shared bank enrollment, compact per-bank balances, and a resizable incoming/outgoing transaction ledger
- Remittances includes a Bank Transfers summary card and lists expense bank-transfer payments as outgoing ledger transactions
- Twenty-row ledger previews with **See full ledger** toggles; the Expenses page grows below the viewport and uses whole-page scrolling when expanded
- Filtered, searchable A4-landscape PDF expense export matching the on-screen ledger with references, MOP, Total Amount, Amount Paid, and Outstanding Amount; 10-point table text, repeated headers, applied-filter and financial summaries, Paid/Unpaid/Partially Paid and overall totals, aligned financial columns, and `ConTracktor_v1` page footers
- Contacts directory
- Employee profiles with birthday/age, contact details, position, class, daily and derived hourly rates, NBI/police/drug-test/biodata compliance, an SQLite-embedded 1x1 picture, attendance history, and outstanding employee advances
- Daily-rate attendance calculation with an unpaid 12:00 noon-1:00 PM overlap, eight regular hours, and ordinary-day overtime at 125% of the derived hourly rate
- Project-head-authorized batch attendance with per-employee custom time-in/time-out, plus the existing employee-PIN kiosk
- Project-head-authorized daily attendance closures, a Monday-Sunday employee payroll accumulator, a separate weekly expense commit, and double-click batch drill-downs with both a one-row-per-employee salary summary and the complete daily attendance detail
- Recoverable employee cash advances with searchable employee selection, Cash or Bank Transfer disbursement, and a complete dated recovery ledger
- Cash and bank repayments reduce an advance's net expense while preserving its original expense and transaction history. Salary deductions settle the employee balance and reduce the separately committed weekly payroll amount, preventing duplicate expense recognition.
- Client deposit and contractor withdrawal ledger with funding progress
- Month calendar and upcoming-event list
- Reusable project-head registry with multi-project assignments and a visible list of registered heads
- Multiple project heads with salted, one-way hashed PINs
- Text export, audit log, and SQLite backup

## Financial and security behavior

- Currency is stored as integer cents to avoid floating-point rounding errors.
- Payments are separate records, allowing unpaid, partial, and paid expense states.
- Dashboard **Contract Value Deposited** is the sum of active client deposits for the selected project scope.
- The nested chart keeps unpaid outstanding commitments separate from recorded payments and warns when outstanding commitments exceed the available deposited budget.
- Expense rows place **Total Amount**, **Amount Paid**, and **Outstanding Amount** together for immediate comparison; unit price remains stored and available in edit/export workflows.
- Expense status is derived from recorded payments; editing an expense cannot bypass payment safeguards.
- Cash payments are limited by spendable shared cash on hand, excluding surrendered cash awaiting deposit, while bank transfers require an enrolled bank with enough balance.
- Recording a payment starts with project-head PIN verification, then displays shared cash on hand and the selected project's payment budget before saving.
- New payment records retain the authorizing project-head ID; legacy payments remain visible as **Legacy / not recorded**.
- Paid batches are checked while staging and checked again immediately before project-head authorization and ledger commitment.
- Every payment is limited by the selected project's remaining deposited budget.
- Expenses and remittances are voided/restored instead of silently deleted.
- Attendance is first closed once per work day and then committed once per Monday-Sunday payroll week. Each weekly commit stores gross wages, advance deductions, net payable, its daily-closed attendance rows, date span, and authorizing project head.
- Employee cash advances remain in the expense ledger. Posted recoveries appear as **Recovered**, reduce **Net Amount**, and never erase the original advance record.
- Salary deductions are staged against available uncommitted payroll and become posted recoveries only when that payroll batch is committed by a project head.
- Project-head and employee PINs are salted and hashed; the original PIN is not stored.
- Registered heads currently use the requested default PIN **0000**. Existing heads are imported and reset to that PIN once during this upgrade.
- **0000 is not suitable for real financial use.** Add a change-PIN workflow and require unique private PINs before production deployment.
- Expense creation, remittance creation, and payroll commit require a project-head PIN and record the authorizer.
- Editing an expense requires a valid PIN from every active head of the affected project.
- Removing a head from a project requires that head's own PIN and keeps the registry identity and historical audit records intact.

## Shared-bank budget model

- A bank account can serve multiple projects.
- Every client deposit identifies a project and an enrolled bank account. Withdrawals identify a bank but enter one shared cash pool.
- The Remittances divider can be dragged to resize the bank-balance and transaction-ledger sections.
- Ledger columns can be resized manually and automatically stretch with the application window.
- Bank balance is deposits minus withdrawals and direct bank-transfer expense payments, plus posted employee-advance repayments received into that bank.
- Both Expenses and Remittances display the same commitment-based **Project Budget Remaining**: project deposits minus every active expense net amount after posted advance recoveries.
- Withdrawals form a shared cash pool across projects. Cash on hand is total withdrawals minus non-bank expense payments plus posted cash advance repayments.
- Petty cash and direct procurement are shared custody allocations, not project budgets. Their sources are assigned automatically from the oldest withdrawal balances first and may span several withdrawal references.
- Every new deposit, withdrawal, bank transfer, expense batch, cash allocation, verification, and surrendered-cash redeposit receives a stable audit reference and an automatic transaction timestamp.
- Each registered project head has one compact petty-cash summary and may hold up to two active petty-cash references globally.
- A cash expense must cite an active allocation with enough balance and must be authorized by the registered head responsible for that allocation.
- Surrendering an allocation locks its entire unused balance. It cannot be spent or returned to unallocated cash; **Deposit All Surrendered** flushes the complete locked amount to one enrolled bank under an `RD` reference.
- Remittances includes project, bank, transaction type, status, date, and free-text/reference filters, while preserving gross withdrawals, cash redeposits, and net withdrawals as separate audit values.
- Recorded payments and bank transfers remain separate cash-flow views and are not deducted a second time from the displayed committed budget.
- Bank balance and project budget are intentionally different views: bank balance is physical funds remaining after withdrawals and transfers, while project budget reserves every active expense commitment across bank and withdrawn cash.
- Bank withdrawals do not require a project selection. They are labeled **Shared Cash Pool** and remain visible when viewing an individual project.
- Contract amount collectible is total contract value minus active project deposits.
- Every active expense reduces the commitment-based project budget by its full total; payments separately track how much cash has actually left the user and how much remains outstanding.
- Existing transactions from older versions remain available and appear as **Legacy / unassigned** when no bank was previously recorded.

The upgrade is additive: it creates new tables, references, timestamps, and status fields without replacing the database or deleting existing records. Before the first shared-cash migration, the app automatically creates a timestamped `*_before_shared_cash_*.db` copy beside the active database. Continue making separate routine backups as well.

This remains a local prototype. Anyone who can copy the database file can access its business data, although they cannot read the original PINs from it. Protect the Windows account, enable full-disk encryption such as BitLocker where available, and save regular backups to a separate drive. A server is unnecessary for one trusted computer, but authentication, encrypted transport, access roles, and managed backups should be designed before multi-computer or internet use.

This is not certified accounting or statutory payroll software. Confirm overtime, break, holiday/rest-day, tax, deduction, and rounding rules before using it for real wages. For the prototype's ordinary-day rule, hourly rate is `daily rate / 8`, actual overlap with 12:00 noon-1:00 PM is unpaid, the first eight paid hours use the ordinary hourly rate, and later hours use 125%.
