# ConTracktor instructions for coding agents

## Authority and scope

- Current behavior is defined by `app.py`, `app_clean.py` and `launch_contracttor.pyw`, not conversation history or older release/workflow notes. This documentation was inspected against application commit `a329efc` (2026-10-07).
- The existing laptop shortcut runs `../Latest_App_Preview_20261003/launch_contracttor.pyw`. Its core files matched this checkout at inspection. That directory holds the live private database. Do not substitute the outer `ConTracktor_v2/app.py`, `Updates/app.py`, historical backups or `app_before_*.py`.
- Before editing, verify the shortcut/launcher, selected database, Git status and whether the live source and this checkout have diverged. Do not silently overwrite one with the other. Use this checkout as the source/documentation repository; changing the laptop's runnable source requires the requested scope and a source backup.
- Repository restructuring has not occurred. Work from the source directory, not `.venv` or cache directories. Do not relocate data, launchers or historical copies as an incidental cleanup.

## Required reading

Read `README.md` and `docs/ARCHITECTURE.md` before application work. Read the relevant module document(s) before changing a workflow. Read `docs/DATABASE.md` and `docs/ACCOUNTING_RULES.md` for any persistence or financial change.

| Change | Additional required module documents |
|---|---|
| Employee identity, deployment or rates | EMPLOYEES, ATTENDANCE, PAYROLL |
| Project lifecycle, budgets or heads | PROJECTS; financial modules affected by the change |
| Attendance grid, logs, corrections or deletion | ATTENDANCE, PAYROLL, CASH_ADVANCES |
| Payroll commitment, payment or reopening | PAYROLL, CASH_ADVANCES, EXPENSES, INTER_PROJECT_FUNDING, CASH_OPERATIONS |
| Advances or employee recoveries | CASH_ADVANCES, PAYROLL, CASH_OPERATIONS, INTER_PROJECT_FUNDING |
| Expense entry, import, verification or payment | EXPENSES, CASH_OPERATIONS, INTER_PROJECT_FUNDING; BANK_TRANSACTIONS for bank payments |
| PC/DP, cash receipts, returns or redeposits | CASH_OPERATIONS, INTER_PROJECT_FUNDING, BANK_TRANSACTIONS |
| Bank transactions | BANK_TRANSACTIONS, CASH_OPERATIONS, EXPENSES |
| Dashboard, billing or reports | REPORTING and every module supplying the changed metric |

Module documents are under `docs/modules/`. For inventory, contacts, progress or calendar, read their architecture/database sections and inspect the active code/tests; dedicated module documents do not yet exist.

## Data and accounting safety

- Never open a client database through `Database` merely to inspect it: construction runs migrations, normalizers and repairs. Use SQLite read-only mode for diagnostics. Use disposable database copies for tests and upgrade trials.
- Never replace live records with a fixture or backup unless specifically authorized. Before an authorized data repair, make a transaction-safe SQLite backup, identify exact records, preserve unrelated newer data, and verify repeat safety.
- Preserve exact integer-cent arithmetic, stable employee IDs, cash-source provenance, committed payroll snapshots, audit trails and historical exclusions. Do not double-count CA issuance and recovered labor, client-direct payments, transfers or reimbursements.
- Supplier payment, project-funding settlement, physical custody, allocation and contract budget are distinct. A status label is not permission to invent or duplicate cash.
- Use supported reversal/reopen methods rather than direct SQL shortcuts. Inspect application and database constraints together; upgraded columns do not all have declared foreign keys.
- Do not treat project-specific historical migration guards or known amounts as general rules. Do not change guards or replay reviewed repairs without explicit data-repair scope.
- Keep SQLite files/sidecars, private records, employee photos, receipts, reports, environment files, credentials, logs and runtime/cache folders out of Git. `.gitignore` is not complete protection; inspect the exact staged paths. Do not broaden this documentation task into ignore-rule edits.

## Implementation and verification

- Preserve unrelated user changes. Use focused patches; do not refactor the monolith or migrate directories without approval.
- Read the active definitions: `PayrollTab` is defined twice, and legacy expense/remittance implementations also remain. Normal startup selects the later active classes and clean presentation layer.
- Add/update regression tests for affected invariants using temporary databases. Run focused tests, then the full `python -B -m unittest discover -p "test_*.py"` suite for cross-module financial changes. GUI tests require a usable Tk environment.
- Before release, test upgrades on disposable copies and follow the selected packaging version's build/security instructions. A test pass is not installer validation or antivirus clearance.
- Update these docs when behavior, schema, launch paths or authority changes. Cite real function/class names and distinguish Implemented, Historical compatibility, Known limitation and Proposed—not implemented. Flag contradictions rather than documenting intended behavior as fact.
- Do not commit, push, package an installer or publish a release unless the user requests it. Never include client data in publication.

## Documentation maintenance

Keep README as the entry point, ARCHITECTURE as the system map, DATABASE as the schema reference, ACCOUNTING_RULES as the financial contract, and module documents as workflow details. Existing release notes remain historical evidence. Do not hard-code current client balances into permanent guidance.
