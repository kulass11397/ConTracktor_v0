# Cash operations

Implemented reference: `app.py`/`app_clean.py` at `a329efc`; inspected 2026-10-07. Read [ACCOUNTING_RULES](../ACCOUNTING_RULES.md) before changing balances.

## Purpose

Make physical cash, allocable sources, project cash ownership and PC/DP custody traceable without treating custody transfers as new costs.

## Current implementation

Cash Operations maintains PC/DP allocations, activity, returns, surrendered/redeposited cash and active allocation overviews. Receipt register/activity is a related view. Physical client receipts can be placed into project cash pool or bank; pending receipt cash is physically held but not automatically allocable. Receipt-derived owner subaccounts are computed from the original receipt and repayments.

`CashAllocationDialog` chooses explicit project/account owner and exact source contributions. Multiple withdrawals may fund one allocation; receipt-owned portions from different projects may not mix. The source list can expand derived RCA owner accounts; these are references over the original receipt, not new database cash receipts.

## Relevant files/classes/functions

`app.py`: `CashAllocationDialog`; `ExpensesTab` cash/receipt/financial-control methods. `Database`: `cash_summary`, `financial_control_position`, `unallocated_cash`, `allocation_balance/spent/returned`, `withdrawal_available`, `manual_cash_source_options`, `validate_manual_cash_sources`, `create_cash_allocation`, `return_cash_allocation_to_pool`, `set_pool_return_voided`, `close_cash_allocation`, `redeposit_all_surrendered`, `set_allocation_surrender_voided`, `set_cash_redeposit_voided`, `place_cash_receipt`, `cash_receipt_project_accounts`, `_sync_allocation_usage_status`, `_reopen_restored_allocations`. `app_clean.py` controls visible grouping and scrolling.

## Database tables and relationships

`cash_allocations` is an owned custody record. `cash_allocation_sources` maps original cash to remittances; `withdrawal_id` also serves as the legacy/first source pointer and may identify a physical receipt, despite its name. `cash_allocation_transactions` stores issuance/payment/return/surrender history. `cash_pool_return_sources` releases exact contributions. `cash_redeposits` and `cash_redeposit_sources` transfer surrendered cash to a bank. `cash_repayment_surrenders` tracks physical employee recovery awaiting deposit. `cash_receipt_placements` ties a receipt to pool/bank. Repayments derive cash ownership; no RCA account table exists.

## Important business rules

- Allocation is not an expense and does not create cash. Sources must be active, date-eligible, owner-compatible, sufficient and sum exactly to issuance.
- Source cutoff metadata can exclude reviewed legacy withdrawals. Production manual sourcing must not be silently replaced by FIFO; the FIFO helper still serves older/tests/support paths.
- Petty cash is limited to two active accounts per responsible head across projects; DP is excluded from that limit and requires supplier/payee. Issuer and receiver remain distinct people even where DP uses single-issuer approval mode.
- Available allocation = original amount minus active expense payments minus active returns/surrenders. Canonical payment/expense eligibility determines spending.
- Return to Shared Pool releases unused custody for reallocation; surrender instead reserves physical cash awaiting deposit. Redeposit is another event, not a new client deposit.
- Positive cash restored by expense void/reopen/source correction must reopen usage status. Startup repairs stale Completed/Fully Used positive balances. Fully returned zero allocations and separate surrender/redeposit custody states remain protected.
- Undo operations must check downstream reuse and custody; they cannot recreate already spent cash.

## Inputs and outputs

Inputs: allocation owner/type/date/amount, source splits, issuer/receiver, supplier/purpose, receipt placement or return/surrender/deposit instructions with authorization. Outputs: allocations/source links, custody transactions and pool releases, placements/redeposits, derived owner-account availability and audit trails. Funds remain in their original receipt/withdrawal provenance.

## Dependencies on other modules

Bank transactions introduce withdrawn cash and receive deposits. Expense/CA payments consume custody. Inter-project repayments reassign receipt-owned cash. Project/head data determines ownership/authorization. Reporting separates physical, reserved, pending and allocable figures.

## Workflow example

Allocate eligible cash to a DP and pay an expense from it. If that expense is voided, its restored allocation balance becomes usable again. Use Return unused cash to shared pool to release that custody; no new withdrawal or receipt is required.

## Known limitations or technical debt

Historical first-source fields coexist with multi-source tables. Global company cash, source availability and project funds use different calculations. Project-filtered `cash_summary` currently subtracts global redeposits and does not use the company historical opening boundary, so do not assume its totals partition company cash. Some labels/counts depend on stored status while balances are calculated; the DP repair addresses specific stale completion labels, not arbitrary corruption. Legacy source repair fingerprints are not generic validation. Source consumption within an allocation follows stored source date order rather than per-payment user-selected sub-splits.

## Important invariants and tests

No new cash from allocation/reimbursement; no mixing multiple receipt owners; exact splits; no reusable cash from surrender alone; no source overdraw; no double restoration; preserve DP reactivation behavior. Tests: allocation/receipt/return/redeposit cases in `test_app.py`, manual source tests in `test_project_funding.py`, `test_wd_repair.py`, `test_allocation_reactivation.py`.
