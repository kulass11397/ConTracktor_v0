# ConTracktor v1.6.11

This cumulative, record-preserving Windows update repairs the reviewed Petty Cash and Direct Procurement withdrawal-reference trail and prevents old legacy withdrawals from being reused by new allocations.

## New and updated features

1. **Guarded one-time WD-reference repair**
   - Uses 24 August 2026 as the curated starting boundary.
   - Relinks the 11 verified PC/DP allocations to their confirmed withdrawals, including the two separate ₱100,000 withdrawals dated 24 August.
   - Preserves every allocation, withdrawal, expense, payment, surrender, redeposit, and financial amount.

2. **Succeeding allocations are included**
   - PC/DP allocations entered after the verified sequence are discovered at first launch.
   - They are matched successively to remaining withdrawals dated 24 August 2026 onward.
   - One withdrawal may fund multiple allocations, and one allocation may be split across multiple withdrawals when amounts require it.
   - A withdrawal must exist on or before the allocation date.

3. **Legacy-source cutoff for future allocations**
   - Withdrawals before 24 August 2026 remain visible and unchanged for audit.
   - They are excluded from automatic WD matching after this repair.
   - Future PC/DP allocations continue from the corrected post-boundary sequence.

4. **All-or-nothing safety checks**
   - The repair runs only if known references, dates, amounts, and legacy links match the reviewed backup.
   - It confirms every succeeding allocation can be fully supported by eligible withdrawals.
   - Any mismatch cancels the whole repair without changing a reference.

5. **Backups and audit history**
   - The updater makes timestamped application and database backups before replacing application files.
   - The app creates an additional WD-repair database backup before changing links.
   - Every corrected allocation receives an audit record containing its old and new WD sources.
   - A durable marker prevents the migration from running twice.

6. **Cleaner allocation controls**
   - The redundant “Selected Allocation” menu is removed.
   - “Allocation Actions” remains the single place for edit, pool return, surrender/close, and pool-return void/restore actions.
   - Compact Petty Cash and Direct Procurement funding labels remain project-neutral; origin remains available in allocation audit details.

## Verification

- 49 automated regression tests pass.
- The reviewed client backup reconciles all 11 verified allocation links and retains the expected ₱50,000 post-boundary remainder.
- A simulated later ₱60,000 allocation correctly splits across the remaining ₱50,000 and a succeeding ₱10,000 withdrawal.
- A second launch performs no additional migration.
- The installer payload rejects SQLite database files.


