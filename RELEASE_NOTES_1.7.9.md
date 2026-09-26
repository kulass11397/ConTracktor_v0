# ConTrackTor v1.7.9 — client reports, allocation visibility, and attendance corrections

This record-preserving update adds an integrated client financial/billing report, improves the Petty Cash & Direct Procurement screen, and makes weekly attendance corrections safer and more complete.

- Adds a date-range **Client summary + billing** report to Expenses > Reports.
- Adds completed attendance that has not yet been committed to payroll as a clearly identified **Staged Weekly Payroll** section, so the current grid can be reported without posting an expense.
- Prevents payroll double counting: once attendance belongs to a committed payroll, it leaves the staged calculation and is represented by the committed payroll snapshot.
- Adds financial summary, weekly cost, running total, phase, category/trade, area, project, payment-source, payroll employee, and daily attendance sections.
- Combines construction-expense reimbursement and the management fee on one billing page. The management fee percentage remains editable and the reimbursement may use outstanding linked inter-project funding, a reviewed manual amount, or none.
- The billing page shows one total due and explains that the construction-cost basis is used only to calculate the management fee.
- Report generation is read-only and does not create an expense, receivable, payment, or inter-project repayment.

- Adds a dedicated dropdown for every active Petty Cash allocation with its holder and spendable balance.
- Adds a separate dropdown for every active Direct Procurement allocation with its payee and spendable balance.
- Adds a Project Grace receipts/deposits box that visibly distinguishes physical cash receipts from bank deposits. Existing records are displayed separately and are not merged.
- Adds a guarded one-time correction for the reviewed duplicate: `BD-20260923-0001` is audit-voided because no bank deposit occurred, while `CR-20260721-0001` and its PHP 125,804 repayment trail remain active.
- Selecting a PC or DP dropdown entry focuses the same allocation in the full activity ledger.
- Attendance correction now includes the work site, so a staged or reopened log can be moved to the correct active project.
- Moving an attendance log also moves its daily-close association, recalculates day/project totals, and is recorded in the correction audit history.
- Weekly employee details now include **Delete Duplicate Log** for completed, uncommitted attendance. Deletion recalculates the day, weekly payroll, and grid from the remaining live records while retaining an audit-log entry.
- Work-site changes and deletions are blocked while attendance is still tied to a committed payroll. Reopen the payroll first so expenses, deductions, and project splits cannot be silently corrupted.
- The installer contains application files only and preserves the current client database.

Verification includes the full regression suite and an isolated copy of the current client backup. The repaired copy reports Project Grace deposited funds of PHP 135,700, retains PHP 125,804 in source-linked repayments, records one audit void for the unused duplicate bank deposit, and passes SQLite integrity checking. The newest backup also reports 78 uncommitted attendance entries, 620 regular hours, 16 employees, and PHP 51,100 gross staged payroll for 19-25 September 2026; the generated PDF was rendered page by page for visual review.

Security status: unsigned prerelease. A local Microsoft Defender scan is performed before publishing, but only code signing and Microsoft reputation can materially reduce future false positives. Never disable Defender or add an exclusion to install the update.
