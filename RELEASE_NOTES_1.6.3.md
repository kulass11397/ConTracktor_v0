# ConTracktor v1.6.3

## Withdrawal-fee accounting

- Bank withdrawals now distinguish **Cash amount** from an optional **Withdrawal fee** (default `0.00`).
- Only the cash amount enters the shared cash pool and linked Petty Cash / Direct Procurement allocations.
- The fee is recorded automatically as a linked, paid expense under `BANK FEES` using the same bank account.
- Bank balance is reduced by cash plus fee exactly once.
- The remittance ledger shows the cash amount, bank fee, and total bank debit together.

## Correcting an existing overstated withdrawal

- A withdrawal can be edited downward when the difference remains unused in its linked allocation.
- If cash was already surrendered, first use **Void Cash Return** on the surrender transaction.
- The edit then reduces the linked allocation principal by the correction amount and retains an audit entry.
- Close the allocation again to record the corrected surrendered balance.
- A linked redeposit, if any, must be voided before its surrender can be voided.

## Safety and compatibility

- Existing client records are retained in `%LOCALAPPDATA%\ConTracktor_v1\Data\contractor_tracker.db`.
- A timestamped database backup and application backup are made before files are changed.
- No `.db`, `.sqlite`, `.sqlite3`, WAL, or SHM file is included in the update payload.
- Schema additions are applied automatically when the updated application opens.
- All prior v1.6.2 features remain included, including cash-return void/restore controls and weekly-payroll PDF export.
