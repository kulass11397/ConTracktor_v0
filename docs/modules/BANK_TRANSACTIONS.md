# Bank transactions

Implemented reference: active `RemittancesTab`/`Database` in `app.py` at `a329efc`; inspected 2026-10-07.

## Purpose

Track bank balances and movements while distinguishing project funding, physical cash receipt and withdrawn cash custody.

## Current implementation

The current remittance page enrolls/edits bank accounts and records bank deposits, physical Cash Received On Hand, shared withdrawals and inter-bank transfers. The transaction form's deposit destination controls bank versus cash behavior; withdrawal sets Shared Cash Pool and allows a separate fee. Historical remittances retain project IDs even for shared withdrawals.

Physical receipts are remittance deposits with `cash_received=1` and no bank debit/credit on receipt. Their later Bank Deposit placement is a linked cash-to-bank event. Surrendered allocations and physical employee recoveries use redeposit workflows. Inter-bank transfers move between enrolled bank accounts without adding project deposits.

## Relevant files/classes/functions

`app.py`: active `RemittancesTab`, `BankAccountDialog`, remittance/transfer form/edit/void methods; `ExpensesTab.place_selected_receipt/deposit_surrendered_cash`. `Database`: `enroll_bank_account`, `edit_bank_account`, `bank_balance`, `create_bank_account_transfer`, `sync_withdrawal_fee_expense`, `reduce_withdrawal_allocations`, `place_cash_receipt`, `redeposit_all_surrendered`, `set_cash_redeposit_voided`. `app_clean.py`: `_clean_remittances`.

## Database tables and relationships

`bank_accounts` holds enrolled account details (private). `remittances` holds deposit/withdrawal records with bank, shared-cash and physical receipt flags, reference, authorization and optional fee expense. `bank_account_transfers` links source/destination banks. `payments` directly debits a bank when bank-linked; CA recovery transactions may credit one. `cash_receipt_placements`, `cash_redeposits` and source tables link physical cash deposited back to bank. Some bank/remittance fields were added without declared FKs; inspect [DATABASE](../DATABASE.md).

## Important business rules

- Positive transfers require different active banks, sufficient source balance and active registered-head authorization.
- Bank balance includes remittances, active bank payments, CA bank recovery, receipt placements, redeposits and inter-bank movements; do not sum only deposits/withdrawals.
- Withdrawal cash amount is principal; fee is a linked bank-paid expense, not more cash withdrawn or deducted twice from principal.
- Depositing already received cash is not a second client payment. Do not create a duplicate project deposit to represent a placement/redeposit.
- Edit/void/restore guards consider dependent allocations, repayments, cash usage and destination/source availability. Inter-bank reversal cannot withdraw money the destination no longer holds.
- Internal project settlement and actual bank movement are different operations.

## Inputs and outputs

Inputs: bank identity, project/deposit destination or Shared Cash withdrawal, date/amount/fee/purpose/reference, transfer banks, head authorization and correction reason. Outputs: bank/remittance/transfer rows, fee expense/payment, updated source availability and bank balances, dependent custody adjustments and audit history.

## Dependencies on other modules

Projects receive funding. Expenses/CAs debit banks. Cash Operations issues allocations from withdrawn funds and deposits custody returns. Funding repayment selects bank availability but does not itself post a transfer. Reporting exposes bank totals separately from project balances and cash holdings.

## Workflow example

Record a client payment as Cash Received On Hand when no bank deposit occurred. Later place its pending amount into Bank Deposit and select the destination bank. Do not add another client deposit for that same money.

## Known limitations or technical debt

Legacy databases may have partial bank schemas; upgrades handle old required name fields and may backfill source bank where only one account exists. Historical statement staging is retained outside current normal workflows. String method matching influences aggregates. No bank API, statement-matching service or full bank reconciliation engine is implemented.

## Important invariants and tests

No duplicate client receipt; exact bank-to-bank conservation; fees do not reduce withdrawn principal twice; source/custody provenance survives edits; no unsafe downstream reversal. Tests: bank/fee/partial-schema/transfer cases in `test_app.py`, source-tracked repayments in `test_project_funding.py`, reviewed link repairs in `test_wd_repair.py`.
