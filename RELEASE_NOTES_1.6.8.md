# ConTracktor v1.6.8

This cumulative patch improves payment-source selection and batch-expense staging.

## Funding-source selection

- Payments / Funding now displays a separate list of every non-void Petty Cash and Direct Procurement allocation.
- Each source shows its reference, type, holder/payee, issuance project, issued amount, calculated remaining balance, and status.
- A source can be selected directly with **Use Selected Allocation** or by double-clicking it.
- Allocations are shared across projects and are no longer hidden solely because an older saved status is stale.
- Zero-balance allocations remain visible for audit clarity but cannot be selected for payment.
- Bank payment sources remain available through **Add Bank / Choose Source**.

## Batch expense drafts

- The Expense Ledger now has a dedicated **Batch Expense Drafts** button.
- Saved manual or imported drafts can be reopened from one consolidated list.
- Drafts show their reference, project, last-saved time, entry count, and imported source file.
- Staged expense rows can be edited with **Edit Selected** or by double-clicking a row.
- Date, amount, item, dimensions, supplier, phase, category, payment state, payment source, and notes can be corrected before commit.
- Staged rows can still be removed without creating ledger or cash activity.
- Editing a staged row recalculates totals and validates available project, bank, and allocation balances without double-counting the old row.
- Saved drafts create no financial transaction until the batch is committed.

## Verification behavior

- Newly committed batch expenses enter the existing expense-verification workflow.
- Editing an already committed expense resets it to **Unverified**, allowing it to be checked and verified again.
- Existing **Verify Selected** and **Batch Verify Unverified** controls remain available.

## Data safety

- This is a code-only cumulative updater; no database is included in the installer.
- Existing client records are preserved.
- Before files are replaced, the installer creates timestamped application and SQLite database backups.
- All v1.6.7 payroll-reopen and v1.6.6 payment-source/PDF features remain included.

## Validation

- Python compilation passed.
- All 45 automated tests passed.
- The installer payload is checked to ensure no `.db`, `.sqlite`, or `.sqlite3` file is included.
