# ConTracktor v1.6.6

## Expense payment and funding-source corrections

- Replaces the single-purpose **Record Payment** action with one compact
  **Payments / Funding** workspace.
- Shows every payment source applied to an expense, together with total paid
  and outstanding amounts.
- Adds **Add Payment Source** so one expense—including a committed weekly
  payroll—can be paid from multiple Petty Cash, Direct Procurement, or bank
  sources.
- If a selected source cannot cover the requested amount, the user can apply
  the available balance and keep the expense correctly marked Partially Paid.
- Adds **Reassign Selected** for correcting a payment posted to the wrong PC,
  DP, or bank source.
- Reassignment updates the original payment rather than adding a duplicate,
  recalculates the old and new allocation balances, updates expense status,
  and records the correction reason in the audit log.
- A source cannot be changed while its allocation has an active surrender or
  return. The user must void that cash return first, which preserves custody
  and redeposit history.

## Payroll PDF scope selection

- Payroll PDF export now asks whether to create **Summary Only** or **Full
  Ledger + Daily Attendance**.
- Summary-only reports contain one consolidated row per employee.
- Full-ledger reports retain the summary and append all daily attendance logs,
  including hours, rate used, overrides, gross pay, and correction count.
- Both options use the existing readable A4 landscape layout, financial
  summary, page numbering, and batch identification.

## Included earlier improvements

- Persistent drafts for batch expenses and batch cash advances.
- Editable staged cash-advance rows and cancel-to-return behavior.
- Cash Advance PDF filters for all recovery methods.
- Withdrawal-fee separation, surrender/redeposit correction controls, employee
  multi-project deployment, attendance corrections, and inventory tracking.

## Record-preserving update safety

- Existing client records remain in
  `%LOCALAPPDATA%\ConTracktor_v1\Data\contractor_tracker.db`.
- The updater creates timestamped application and database backups before
  replacing application files.
- The release payload contains no `.db`, WAL, or SHM files.
- Schema changes are additive and are applied when the updated app first opens.
