# ConTracktor v1.6.10

This cumulative, record-preserving Windows update adds a controlled way to correct PC and DP allocations without treating the correction as a cash surrender.

## New and updated features

1. **Return unused allocation cash to the Shared Pool**
   - Supports both Petty Cash and Direct Procurement allocations.
   - Supports a full or partial amount.
   - Records a unique `PR-YYYYMMDD-####` activity reference, date, amount, reason, recorder, allocation reference, and originating withdrawal sources.
   - Immediately reduces the allocation's spendable balance and restores the same amount to Shared Unallocated Cash.

2. **Pool return is separate from surrender and redeposit**
   - It does not create an expense, payment, bank transaction, withdrawal, surrendered-cash balance, or redeposit.
   - The original withdrawal and its total remain unchanged.

3. **Void or restore a pool return safely**
   - A mistaken pool return can be undone from Allocation Activity.
   - Undo is blocked if the returned cash or its withdrawal-source capacity has already been reallocated.
   - Reopening a fully returned Petty Cash account is blocked if the holder already has two other active PC accounts.

4. **Petty Cash slot recovery**
   - A fully returned PC allocation closes and frees one of the holder's two active PC slots.
   - Direct Procurement allocations remain excluded from the two-PC limit.

5. **Cleaner allocation actions**
   - Edit, Return to Pool, Surrender/Close, and Void/Restore Pool Return are grouped under one Allocation Actions menu.
   - The cash summary now distinguishes “Surrendered awaiting deposit” from cash internally returned to the shared pool.

6. **Clear Direct Procurement funding labels**
   - DP choices display `DP reference | supplier/payee | remaining balance`.
   - The creation project is retained only as audit context in the expanded allocation list ("Created under ...").
   - The project selected on the expense remains the project used for project costing.

## Intentionally unchanged

- Shared bank withdrawals remain visible across projects in Remittances.
- No bank-withdrawal Project dropdown change is included.
- Existing expense, payroll, remittance, allocation, contact, and inventory records are preserved.

## Verification

- 49 automated regression tests pass.
- The installer payload rejects SQLite database files.
- The updater creates timestamped application and database backups before replacing application files.
