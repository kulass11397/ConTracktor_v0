# Cross-project funding and shared weekly payroll

## Expense funding

1. In Add Expense Batch, choose **Expense project**: the project that received the goods or work.
2. Choose **Funding project**: the project whose available deposited funds will pay for it. It defaults to the expense project.
3. Choose the actual PC/DP allocation or bank account separately. Allocations remain shared cash custody records, not project expenses.
4. Stage and review the batch. The confirmation lists the project funds being used. Only actual paid amounts create borrowing records.

If Oasis pays for Grace, the supplier expense belongs to Grace. Grace shows its actual Paid/Partially Paid status plus an amount owed to Oasis. Oasis has a linked recoverable row. That recoverable row is excluded from expense totals; the same supplier expense is not counted twice.

Unpaid expenses create no money movement or loan yet. Their funding-project selection is an intention for the later payment. Payments/Funding Sources can change the actual funding project and PC/DP reference with the existing expense-edit authorization and balance checks. Repaid loans must have their repayments undone before their funding/payment can be reversed.

The expense import template now includes **Funding Project (blank = expense project)**. Existing forms without this column still work; they default to the expense project. New templates include its project dropdown. Supplier remains optional/free-text.

## Repaying another project

Use Expenses > Inter-project Funding, select the borrowing, and choose Record Repayment. Include a supporting reference and the real repayment date. The amount must not exceed the balance owed or the borrower's available project funds.

This is an internal project-funds settlement: it restores the lender's available funds and reduces the borrower's available funds, without creating another supplier expense, withdrawal, or PC/DP consumption. If cash actually moves between bank accounts, record that movement separately using the existing bank-transfer workflow and reference it here. Do not also enter a new expense for the repayment.

Undo Selected Repayment retains its history, but requires sufficient funds still available to the lender. Reversed expense funding remains visible as history rather than being deleted.

## Workers on multiple projects

Deploy existing employees to every applicable project first. In Batch Attendance, select the work project beside each employee. For a split day, add another segment and enter non-overlapping times, such as Oasis 08:00–12:00 and Grace 13:00–17:00. The system checks deployment dates and rejects overlapping work.

Regular hours are shared across the employee's day, not restarted for each project. The existing eight-hour regular-day/lunch/overtime rules and project deployment rates are retained. Adding or correcting staged segments recalculates the day's regular/overtime split. Existing committed attendance is not silently rewritten.

Close daily attendance in every project before committing the week. Work weeks remain Saturday–Friday.

## One weekly deduction, separate project payrolls

The payroll review shows related projects' gross pay, CA deductions, corrections and net payable. Confirm the included project payrolls using the existing payroll PIN policy. The selected commits are atomic: if one fails, none is posted.

An employee's eligible scheduled CA deduction and weekly cap are calculated once across the week, then distributed in proportion to gross earnings by project. Rounding uses exact cents; negative corrections reduce the available deduction capacity so a project does not produce negative employee net pay. Future-dated advances are not deducted from an earlier week.

Example: Oasis gross 3,000 + Grace gross 2,000, with an eligible 1,000 deduction, gives deductions 600 + 400 and unpaid payroll expenses 2,400 + 1,600. The remaining payday cash requirement is 4,000, not 5,000. The earlier advance remains recorded as money already paid.

If that advance originally came from Oasis, the 400 recovered through Grace creates a linked project recovery owed to Oasis. Project cost attribution is still 3,000 for Oasis and 2,000 for Grace; company-wide costs remain 5,000.

In the Expense Ledger, select the week's unpaid project payroll expenses and choose **Pay Selected Weekly Payrolls** under Selected Expense actions. Choose one shared PC/DP allocation and either each expense project's own funds or one funding project. The allocation is consumed only by the payments actually recorded. Insufficient total funding blocks this full-distribution operation; use the existing Payments/Funding Sources feature for partial or multiple-source payments instead.

The payroll total equals an allocation only when that allocation was issued for exactly that payroll and has no other spending. Excess allocation cash remains available; it is not forced into payroll. Filing a withdrawal or issuing a DP allocation does not automatically mark wages paid.

## Corrections and record retention

Once a shared week is committed, its employee-wide deduction split is locked. Reopen **all affected project payrolls** before changing multi-project attendance, rates or CA deductions, then review and recommit them together. Reopening only one project does not silently redistribute deductions already posted elsewhere. Repayments on related project loans must be undone first.

Previously committed payroll history is not retroactively converted to proportional deductions. Older multi-project weeks with posted deductions require the existing reopen/review workflow before recalculation.

The upgrade is additive and automatically creates a SQLite snapshot before adding the new project-funding tables to an existing database. It does not replace the client's database with sample data. The existing launchers and database-selection behavior are retained.

## Validation

90 automated tests cover the existing 49 regression cases, shared project funding/payroll, explicit withdrawal splits and the reviewed one-time repair. Disposable clean-interface checks cover the funding tab, paid batch insertion, manual WD selection, drafts, payroll review, and preserving attendance inputs on cancellation/invalid values.

A copy of the supplied 17 September backup was upgraded. All non-source historical fields/records were preserved, including 1,270 expenses, 69 remittances, 24 allocations, 475 attendance logs and 8 payroll batches. Only reviewed withdrawal links, their dependent return/deposit source trails, audit entries and migration markers changed. Cash totals and database integrity checks passed. Original client/local databases were byte-for-byte unchanged.

The v1.7.0 updater contains no replacement database. Close the existing app, export a fresh backup, install under the same Windows user, and reopen the existing shortcut. The guarded one-time repair applies 21 reviewed allocation trails; any changed reviewed amount/date/status/link safely skips the September repair. It does not guess at newer entries absent from the reviewed backup.

## Manual withdrawal sourcing

When creating a PC/DP allocation, select one or more WD checkboxes and enter how much of each withdrawal is used. The contributions must exactly equal the allocation amount. References are listed in the confirmation and stored with their exact amounts. Voided/future/depleted withdrawals are blocked, and the repaired client's pre-24-August legacy withdrawals remain excluded from issuance. Pool-returned cash retains its original WD provenance when selected again; surrendered/redeposited cash is not silently made available.

The one-time repair retains the July migration allocations and all financial amounts. The two user-confirmed cancelled September 7 DP attempts trace to the voided 37,000 withdrawal for audit only and have zero net source usage; the final purchase traces to the new September 8 withdrawal. The returned September 4 DP releases 63,050 from its original source, then its replacement uses that cash plus the remaining 200 to make 63,250. Related return/redeposit source links are repaired together, and repeating the migration is a no-op.
