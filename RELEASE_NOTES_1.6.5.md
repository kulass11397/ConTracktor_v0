# ConTracktor v1.6.5

## Persistent batch drafts and safer confirmation flow

- Adds **Save Draft** and **Open Draft** to batch cash advances and batch
  expenses.
- Drafts remain in the client's current database and have no effect on the
  expense ledger, cash on hand, bank balances, or employee balances until
  authorized and committed.
- Re-saving updates the same draft reference; successful use marks the draft
  committed for audit history.
- Cancelling final confirmation or authorization reopens the previous batch
  window with its staged rows and selections retained.
- Validation errors after review also return to the staged batch instead of
  forcing the user to re-enter it.

## Editable staged cash advances

- Adds **Edit Selected** and double-click editing to the staged employee list.
- Amount, purpose, repayment method, and optional weekly deduction limit can
  be corrected before commitment.
- The effective date and funding source remain shared batch fields and are
  retained when editing or reopening a draft.

## Cash Advance PDF export

- Adds **Export Advances PDF** to Payroll > Cash Advances.
- Uses a compact popup so the main Cash Advances screen stays uncluttered.
- Repayment-method checkboxes support any combination of:
  - Salary Deduction
  - Cash Repayment
  - Bank Repayment
  - Manual / Mixed
- Includes Select All and Clear actions.
- The searchable A4 landscape PDF contains a cash-advance balance table and the matching recovery-transaction history.
- Each report includes total advances, recovered amount, outstanding amount, and pending salary deductions.

## Withdrawal fee and surrender correction (included from v1.6.3)

- Bank withdrawals distinguish physical **Cash amount** from a customizable **Withdrawal fee** that defaults to `0.00`.
- Only physical cash enters the shared cash pool and PC/DP allocations.
- The fee becomes a linked, bank-paid `BANK FEES` expense.
- Cash plus fee reduces the selected bank account exactly once.
- Existing overstated withdrawals can reduce unused linked allocation principal after any redeposit and surrender are voided in the correct order.

## Safety

- Existing records remain in `%LOCALAPPDATA%\ConTracktor_v1\Data\contractor_tracker.db`.
- The updater makes timestamped application and database backups first.
- The payload contains no database, WAL, or SHM files.
- The self-contained updater includes the bundled runtime and applies additive schema changes on launch.
