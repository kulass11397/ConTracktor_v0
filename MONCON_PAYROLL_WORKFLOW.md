# MONCON company-wide batch workflow

Employees belong to MONCON, not exclusively to a work project. The payroll ledger defaults to all employees/all projects.

## Batch attendance
Open Batch attendance without selecting a top-level project. All active employees are listed. Select the actual work project for each time segment. Prior deployment is not required for manual batch attendance.
For a split day, enter 08:00–12:00 at Oasis and add a segment 13:00–17:00 at Grace. Times must not overlap across any work sites. Lunch 12:00–13:00 is unpaid. The eight-hour regular limit is shared across the whole employee day.
A valid work-project rate takes precedence; otherwise the employee's standard rate is used. Close each work site's daily attendance to include its shifts in staged weekly payroll.

## Batch cash advances
No top-level project is required. Every active MONCON employee can receive an advance regardless of home or deployment project.
Choose Funding project in the batch window to identify the budget/expense ledger funding the advance, and choose its actual payment allocation or bank. That field does not affect which employees are available.
Save Draft stores funding and staged entries without moving money. Open Draft lists company-wide advance drafts, including older project-specific drafts. Cancelling authorization preserves the staged payload.

## Weekly deductions
Salary Deduction advances are recovered once per employee, capped by eligible available weekly pay and configured weekly deduction caps. The employee-wide deduction is allocated proportionally to gross wages earned at each work project, with exact-cent rounding. A worker with no closed attendance cannot yet have a payroll deduction applied; their outstanding advance remains visible.
Weekly payroll expenses remain separate for each work project and can be paid using multiple recorded sources. Cash Repayment/Bank Repayment/Manual methods are not automatically treated as scheduled salary deductions.

## Update safeguards
Existing financial and attendance history is retained. This patch does not repair client withdrawal matches or change historical amounts. Back up first, close the app, and install under the same Windows user. Stop on any Defender detection; security review is separate from application correctness.
