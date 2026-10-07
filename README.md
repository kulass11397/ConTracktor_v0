# ConTracktor — current application and project documentation

Local Windows contractor-management system for projects, expenses, petty cash, remittances, company-wide attendance/payroll, advances, inventory and contacts.

This repository documents the application used by the **ConTracktor - Current Working Copy** desktop shortcut, before repository restructuring. The current application is based on GitHub commit `a329efc` on `ConTracktor_v1` and includes the later weekly attendance roster/workbook changes documented below. The earlier historical checkpoint is the unchanged `baseline-2026-10-07` Git tag.

## Documentation map

Start with [agent instructions](AGENTS.md), [architecture](docs/ARCHITECTURE.md), [database](docs/DATABASE.md), and [accounting rules](docs/ACCOUNTING_RULES.md).

| Module | Current workflow documentation |
|---|---|
| Employees | [Identity, deployment and rates](docs/modules/EMPLOYEES.md) |
| Projects | [Lifecycle, heads and budgets](docs/modules/PROJECTS.md) |
| Attendance | [Weekly grid, shifts and corrections](docs/modules/ATTENDANCE.md) |
| Payroll | [Commitment, payment and reopening](docs/modules/PAYROLL.md) |
| Cash advances | [Grants, deductions and recoveries](docs/modules/CASH_ADVANCES.md) |
| Expenses | [Entry, imports, funding and verification](docs/modules/EXPENSES.md) |
| Cash operations | [PC/DP, receipts, returns and custody](docs/modules/CASH_OPERATIONS.md) |
| Inter-project funding | [Borrowing, repayment and ownership](docs/modules/INTER_PROJECT_FUNDING.md) |
| Bank transactions | [Deposits, withdrawals and transfers](docs/modules/BANK_TRANSACTIONS.md) |
| Reporting | [Financial figures, summaries and billing](docs/modules/REPORTING.md) |

These describe current code, not every historical proposal. They flag older-note conflicts and separate general behavior from client-specific compatibility repairs. Local record totals and bespoke billing PDFs are not permanent accounting rules.

The last packaged updater is [v1.7.12](https://github.com/kulass11397/ConTracktor_v0/releases/tag/v1.7.12). This baseline is a source checkpoint; it does not replace that installer or create a new executable release.

## Changes since v1.7.12

- Added **Personal** to the default project phases so company-owned expenditure can use a dedicated phase.
- Existing projects receive a Personal phase when the database opens. The operation checks for an existing phase without regard to letter case, so reopening the app does not duplicate it.
- Newly generated batch-expense import workbooks include Personal in the phase dropdown. Existing multi-project and client-funded import behavior is retained.
- Updated the phase regression test to require the Personal phase and the new default phase count.
- Preserved the current working-copy launcher as `launch_contracttor.pyw`. It selects the working database explicitly, supports an alternative database through `CONTRACTOR_LAUNCH_DB_PATH`, and records startup failures in `launch_error.log`.
- Added `run_working_copy.bat` as a portable launcher for this source checkpoint. It uses a local virtual environment when available, or Python from PATH, without a developer-specific absolute path.
- Added a weekly batch-attendance workbook generated from the active project/site rosters. It uses one tab per active project, supports `P`, `A`, custom/split times and additional-employee dropdowns, and can be round-tripped through Google Sheets before `.xlsx` import.
- Weekly workbook import validates the complete file and stages it in the existing grid without bypassing draft saving, project-head authorization, overlap checks or payroll finalization.

The current UI, weekly attendance grid, payroll, cash-advance attribution, project receipt ownership, inter-project reimbursements, client-funded expense entry, and multi-project imports remain part of the preserved application. Earlier changes are documented in the release and workflow notes below.

## Local record corrections associated with this working copy

The local working database also includes reviewed corrections for consumed direct-procurement allocations, the relationship between payroll payments and their original funding allocations, architectural and geological service balances, expense ownership, and a premature payroll reimbursement.

These are corrections to private operational records. The database and correction scripts are not included in this source checkpoint, and checking out this baseline does not replay those standalone corrections. Existing database-upgrade logic within the application is retained unchanged. Keep the corrected working database and its backups separately when preserving or restoring the local system.

The local financial and billing PDFs created alongside this working copy, and their standalone generation tools, also remain separate from the application source checkpoint.

## Authoritative application and launch instructions

- `app.py`: application workflows, calculations, persistence, and built-in exports.
- `app_clean.py`: the current presentation layer and scrolling behavior.
- `launch_contracttor.pyw`: working-copy entry point and explicit database selection.
- `test_*.py`: maintained automated regression tests using temporary test databases.
- `packaging/`: existing release recipes and installer/launcher source.

For the existing laptop installation, continue using **ConTracktor - Current Working Copy**. That shortcut uses the corrected local `contractor_tracker_preview_135800.db`; this file is intentionally excluded from Git.

For a separate checkout, install Python with Tkinter, provide an appropriate private database, and run `run_working_copy.bat`. The launcher defaults to `contractor_tracker_preview_135800.db` beside the source. To use another database, set `CONTRACTOR_LAUNCH_DB_PATH` to its full path before launching. Without an existing database at the selected path, the application can initialize a new database; that is not a restoration of client records.

The core application uses Python's standard library and Tkinter. A typical development check is:

```text
python -B -m unittest discover -p "test_*.py"
```

The current working tree passed 183 automated tests on 2026-10-07. This is a dated source-level result, not installer validation or a promise that future edits are tested. Tests use disposable databases; never aim them at the working client database. Constructing `Database` runs upgrades and repairs. See [database safety](docs/DATABASE.md).

Known architectural limits include a monolithic core, duplicate/legacy class definitions, string-based financial classifications, mixed database/application constraints, and guarded client-specific startup repairs. This is a local operational tracker, not a complete double-entry accounting or automatic revenue-recognition system. Documentation does not implement new features.

## DP allocation reactivation patch — 2026-10-07

- Voiding an expense immediately refreshes its original PC/DP allocation: restored cash reopens it as Active or Partially Used and clears its closure date.
- Restored cash can be returned through Cash Operations > Return unused cash to shared pool. It is not automatically moved or duplicated.
- Opening the application repairs stale Completed/Fully Used allocation labels only when an available balance remains. Payment amounts, cash-source links and expense records are not rewritten by this repair.
- Restoring a voided expense checks available allocation funds first, preventing a second use of money already returned or consumed.
- Surrendered, redeposited and voided allocations retain their separate custody workflow. Fully returned allocations remain closed.
- Added regression coverage for full/partial voids, restoration, return-to-pool and repeat-safe startup repair.

This patch updates source only; it does not publish a new installer. The historical baseline tag remains unchanged.

### Historical baseline application fingerprints

The following SHA-256 values identify the application files at `baseline-2026-10-07`, before the DP reactivation patch:

```text
app.py        4bb5459c2d6b04e613ab7dde8da138566cd74b93716ac69549931dc190df23a1
app_clean.py  449f77acfbed2a3d5a205a68287079783c52f4d85651290fae2320bbf2f8b12b
```

## Previous release and privacy notes

The v1.7.12 updater allows one generated expense-import workbook to contain rows for multiple expense projects and funding projects. On commitment, rows are separated into auditable project-specific batches.

See [release notes](RELEASE_NOTES_1.7.12.md), [client update guide](UPDATE_GUIDE_1.7.12.txt), and [security review](SECURITY_REVIEW_1.7.12.md).

All earlier feature, development, and deployment documentation is retained in [historical notes](HISTORICAL_FEATURES.md). Use the current guide for installation; older release references there are history, not recommendations.

The standard Inno Setup updater backs up the existing app/database and packages no client records. Installation tests belong to executable release preparation; this source checkpoint does not claim a new installer validation or Defender scan.

Do not commit operational SQLite files or their WAL/SHM companions, employee/client datasets, receipts, uploaded documents, generated reports, environment files, credentials, or signing keys. Any existing client-specific compatibility logic in source should receive a separate privacy review before repository restructuring or further generalization.

The proposed clean repository migration has not been performed. Historical copies, the Python environment, private records, and desktop shortcut remain in their existing local locations.

Security notice: local Defender scans are not Microsoft clearance or a guarantee of acceptance on another computer. Do not bypass antivirus protection. See [review status](SECURITY_REVIEW_1.7.12.md).
