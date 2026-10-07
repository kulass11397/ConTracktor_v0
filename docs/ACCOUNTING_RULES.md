# Accounting rules and financial invariants

Implementation reference: `app.py` at `a329efc`, inspected 2026-10-07. This describes the operational tracker, not a certification of accounting or payroll-law compliance. Do not infer entries from old conversation amounts.

## Distinct concepts

| Figure/event | Meaning | Must not be confused with |
|---|---|---|
| Expense project | Project owning the cost | Project supplying money |
| Funding project | Project funding a recorded payment/advance | Supplier or client |
| Supplier payment | Amount posted against an expense | Repayment to another project |
| Client-direct payment | Supplier settled by client; project cost retained | Company cash spent or client cash received by company |
| Client receipt | Bank deposit or physical receipt recorded in remittances | Construction cost or automatically recognized management-fee revenue |
| Inter-project repayment | Debt settlement and project ownership reassignment | New expense, new client receipt, or automatic bank transfer |
| PC/DP allocation | Reserved/custodial cash with source links | Expense or additional cash introduced |
| Cost budget | Contract spending limit less attributed commitments | Bank balance, available funds or physical cash |
| Project payment-basis balance | Deposits less adjusted recorded payments | Cash physically held for that project |

## Units and record eligibility

Money is integer centavos (`*_cents`). `cents` uses Decimal and ROUND_HALF_UP; preserve exact cents and deterministic proportional remainder allocation. Dates are generally ISO text; local transaction times and SQLite-created timestamps are not a uniform timezone-aware system.

Active expense calculations normally require `expenses.voided=0`; active payments additionally require `accounting_excluded=0`. Posted CA recovery requires `posted=1`, nonvoid transaction and nonvoid advance. Payroll-loan activity depends on the committed batch and expense; ordinary funding-loan activity depends on its payment and expense. Do not sum historical/superseded rows as active costs. Transaction history is retained even where a linked payment is no longer financially active.

## Expenses and construction cost

`record_project_payment` records only a positive amount up to the outstanding expense. Cross-project funding produces one expense plus linked lender/borrower views through `project_funding_loans`; these are not two construction expenses. Client Funded/Client Paid Direct entries settle the supplier for project-cost reporting but carry no bank/allocation consumption and no cross-project debt from that payment.

`expense_ledger_amounts` computes:

```text
recovered = physical CA recovery + salary CA recovery
cost = max(0, expense total - recovered) + payroll deduction attribution
settled = max(0, recorded payments - recovered) + payroll deduction attribution
supplier outstanding = max(0, cost - settled)
```

Report construction costs deliberately exclude CA issuance rows and add back relevant payroll deductions. This differs from blindly summing expense table totals. Phase/category/area/project summaries regroup the same cost: never add those grouping totals together.

Personal phase/category is a classification. It does not automatically transfer cost ownership to Montarra or exempt an item from every report's fee basis. Company-owned purchases must have the intended expense project explicitly selected.

## Payroll and advances

Weeks run Saturday–Friday. Draft/blank grid cells do not earn pay; finalized shifts drive gross earnings. Paid time excludes overlap with 12:00–13:00 lunch; the employee-day regular limit is shared across work sites. Project-effective rates override the employee fallback. Day-type multipliers are implemented calculations, not a claim of complete legal coverage.

```text
net payable = gross wages - applied CA deductions + payroll adjustments
```

Commitment creates project payroll batches and net-payable expenses, not payment cash. Paid status requires subsequent recorded payment (or zero net). The weekly CA plan is employee-wide: eligible scheduled advances FIFO, cap per advance, no future advance before the eligible week end, no deduction above available earnings. Exact-cent shares are distributed by project gross; negative adjustments limit deduction capacity. The first committed project locks the employee-week attendance/deduction signature, preventing independent later reallocation.

An advance initially belongs to its funding project. When salary recovery belongs to another work project, CA-recovery loans transfer cost attribution and record the debt. Never count both the issuance and recovered payroll portion as new construction cost. Cash/bank recovery is a physical return; salary recovery is not a new physical receipt.

Reopening payroll preserves snapshots, excludes old payments, reverses linked allocation-payment transactions, returns deductions/adjustments to pending and detaches attendance for correction. Replacement batches link back to prior batches. Active loan repayments must be undone first. All affected project payrolls must be reopened before changing a locked multi-project employee week.

## Project balances

`project_budget` returns deposits, adjusted payments and their difference. Adjusted payments exclude client-direct payments, subtract project recoveries and include the inter-project funding adjustment. Its deposit query includes active physical receipts as well as bank deposits. `project_commitment_budget` uses active expense commitments minus recoveries. `project_cost_budget` uses contract value minus those commitments with CA-recovery cost reattribution. These functions are not interchangeable.

Loan outstanding is `max(0, principal - active repayments)` for active loans. Settlement to suppliers and settlement to funding projects must remain separately visible.

## Physical cash, receipts and source ownership

A physical receipt is `remittances.type='Deposit'` with `cash_received=1`; it is not a bank deposit. Pending cash is visible in physical custody but cannot silently fund expenses. Authorized `cash_receipt_placements` put it into Project Cash Pool or Bank Deposit, bounded by receipt availability. Placing/depositing the same receipt is not another client receipt or increase in contract funding.

`cash_summary` operational company cash is based on the optional reviewed opening boundary, active withdrawals and pool-placed receipts, less applicable cash payments and redeposits, plus physical cash recoveries. Salary deductions and client-direct payments are excluded from physical spending. Project-filtered cash additionally uses ownership-transfer adjustments; the boundary's opening is company-wide, not individually allocated historical project cash. Known limitation: the current project-filtered method also subtracts the global redeposit total, without a project-specific redeposit filter. Project cash results therefore are not guaranteed to partition the company cash balance; document this behavior rather than silently treating it as reconciled project custody.

`financial_control_position`:

```text
physical cash = operational cash + pending physical receipts
allocable cash = max(0, operational cash - remaining PC - remaining DP - surrendered cash)
```

Pending receipt, reserved allocation and surrendered cash must not also be counted as freely allocable. `unallocated_cash` uses operational cash less allocation balances and surrendered awaiting deposit. Source availability and global allocable totals are separate checks; an unmatched historical/global figure is not permission to invent a source.

Cash-receipt repayments transfer borrower ownership to lender ownership but do not increase company cash. `RCA-...` account references are derived from the original receipt and ownership; they are not newly issued physical receipts. One PC/DP owner cannot mix receipt-owned cash of multiple projects. Shared withdrawals can contribute to an allocation with an explicit owner. Selected source contributions must exactly equal the allocation.

## PC/DP lifecycle and reversals

```text
allocation balance = max(0, original allocation - active expense payments - active returns/surrenders)
```

`allocation_spent` reads canonical payments joined to active expenses, not merely the allocation transaction log's void flag. Source rows reserve the original amounts. Return-to-pool records release exact source contributions; physical surrender does not release reusable pool funds, and redeposit moves surrendered cash to bank custody.

At `a329efc`, expense void/restoration synchronizes allocation status. Positive restored balance becomes Active/Partially Used with closure cleared. Startup repairs stale Completed/Fully Used labels with positive balance without changing amounts. Restoring an expense cannot reuse money already returned/spent. Surrendered, Returned, Redeposited and Voided allocations retain custody guards; fully pool-returned zero balances retain their closed status.

Never restore a return/redeposit or change a payment source without checking whether dependent cash has already been used. A financial reversal can require undoing later operations first.

## Bank balances and transfers

`bank_balance` = active bank deposits minus withdrawals + redeposits + receipt-to-bank placements - active bank-linked expense payments + posted bank CA recoveries + inbound inter-bank transfers - outbound inter-bank transfers. Withdrawal fee is a linked bank expense, separate from the cash principal withdrawn.

Inter-bank transfers affect the two banks, not project deposit totals. Inter-project repayment from Bank Account is an ownership/funding settlement record, not an automatic `bank_account_transfers` posting. Record an actual bank movement separately when appropriate and reference it; do not duplicate supplier payments or deposits.

## Management fee, reports and historical compatibility

`build_expense_billing_context` computes a configurable percentage (default 15) of its report construction basis plus reimbursement selected from outstanding ordinary expense-funding loans, a manual amount or None. It is read-only presentation; it does not post fee income, accounts receivable or a payment. Do not assume the old Grace arrangement's tools/equipment exclusions are universally enforced by that calculation. Classification and project/report selection matter.

Receipt metadata can classify reimbursement, management fee and client credit. It is not automatic revenue recognition and may contain reviewed historical labels that diverge from later ownership movements. Retained receipt balance is not necessarily all management fee.

Historical compatibility includes guarded withdrawal reference repairs, deduction repairs, reviewed Grace records/deposit voids, receipt placement backfills and a live-cash opening boundary. Old imported expenses remain reportable even when not replayed into current source availability. Preserve fingerprints, markers, backups and original history; do not apply a client-specific bridge to unrelated databases.

## Verification references

Use `test_project_funding.py`, `test_company_payroll.py`, `test_company_batches.py`, `test_weekly_grid.py`, `test_expense_summary.py`, `test_wd_repair.py`, `test_allocation_reactivation.py` and relevant `test_app.py` cases. Documentation of a rule is not sufficient: new changes must retain its corresponding financial tests. This system is not a full journal/general-ledger accounting implementation.
