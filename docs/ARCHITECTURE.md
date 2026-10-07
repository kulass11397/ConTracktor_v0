# Architecture

Inspected against the current working tree based on application commit `a329efc`, 2026-10-07. Current code overrides historical prose; see [agent instructions](../AGENTS.md).

## Application shape and authority

ConTracktor is a local Windows-oriented Tkinter desktop application with SQLite persistence. There is no application server, cloud database or synchronization service in the current core. Runtime workflows and built-in PDF/CSV/XLSX handling use the Python standard library; image conversion and packaged launch/build paths can use platform-specific facilities.

The maintained Git checkout is presently `Updates/github_publish_v1.6.3`, despite its historical folder name. The laptop shortcut runs `Updates/Latest_App_Preview_20261003`. `app.py` and `app_clean.py` matched between them at inspection. The live data file is `contractor_tracker_preview_135800.db` beside that preview source. Outer source copies and historical backups are not authoritative. No directory restructuring is implemented by this documentation.

## Launch and persistence flow

```text
Desktop shortcut / run_working_copy.bat
  -> launch_contracttor.pyw
     -> CONTRACTOR_DB_PATH and working directory
        -> app.py __main__
           -> app_clean.create_startup_backup
           -> CleanContractorApp (subclass of ContractorApp)
              -> Database: backups, connection, schema upgrades/repairs
              -> Tkinter pages and dialogs
                 -> Database workflows / SQL -> SQLite
                 -> refresh_all -> recalculated views
                 -> report helpers -> PDF/CSV/XLSX/text files
```

`launch_contracttor.pyw` prefers `CONTRACTOR_LAUNCH_DB_PATH`, otherwise selects the preview-named database beside itself. It sets `CONTRACTOR_RECONCILIATION_PREVIEW=1`, changes working directory, adds the source to the import path and runs `app.py`; startup failures are logged. `resolve_db_path` also supports `CONTRACTOR_DB_PATH` and searches known filenames in nearby directories when no explicit file is supplied. A missing explicit database can initialize an empty system, not restore client records.

`app.py` normally imports the clean UI and takes a SQLite startup snapshot. An `ImportError` falls back to `ContractorApp`. `app_clean.py` imports the core, replaces the tree factory's local wheel handling, reorganizes controls/cards and adds scrolling; it reuses core workflows. It is a presentation subclass, not a separate financial engine. UI rearrangement depends on labels/widget structure and must be verified after core UI changes.

## Source responsibilities

| Source | Responsibility |
|---|---|
| `app.py`: helpers | Money/date/rate calculations, shift pay, report summaries/billing, exports, import workbook parsing/generation |
| `app.py`: `Database` | Schema evolution, historical repairs, identity, financial calculations and many transactional business operations |
| `app.py`: `ContractorApp`, `BaseTab`, dialogs | Project context, authorization, page lifecycle, forms, validation and some direct SQL posting |
| `app_clean.py`: `CleanContractorApp` | Current navigation, grouped action menus, financial detail toggles and scroll behavior |
| `launch_contracttor.pyw`, batch launchers | Runtime/data selection and startup error handling |
| `test_*.py` | Temporary-database and Tkinter workflow regressions |
| `packaging/` | Versioned installer recipes, launch/build code and release checks; not runtime authority |

`PayrollTab` appears twice in the core; the later definition is active. `LegacyExpensesTab` and `LegacyRemittancesTab` remain but are not the current expense/bank pages. The legacy attendance dialog remains even though the active batch action opens the weekly grid. Source searches must distinguish definitions from reachable workflows.

## Workflow boundaries

- Employees retain company-wide identities. Assignments supply effective project rates; attendance records the actual work project.
- Attendance drafts/preview do not create payments. Finalized attendance is closed, then committed to project payroll; commitment creates an expense, not a cash disbursement.
- Payroll deductions recover prior advances. Shared employee-week plans preserve proportional project attribution and exact cents.
- Expenses own the construction cost; payments identify funding and source. A different funding project creates a linked loan rather than a duplicate expense.
- Cash receipts identify client funds received. Placement chooses allocable project cash or bank; reimbursement transfers project ownership without creating cash.
- PC/DP allocates custody of traceable cash, not another cost. Payments consume it; pool returns release it; surrender and redeposit are separate custody events.
- Reporting aggregates the above, including derived attribution rows. Different views deliberately answer different questions.

Detailed workflows and invariants are in [accounting rules](ACCOUNTING_RULES.md) and the [module index](../README.md#documentation-map).

## Other implemented pages

`InventoryTab` uses `inventory_items`/`inventory_transactions` for Consumable opening/restock/usage and Non-Consumable tool borrowing/return. Employee borrowers and linked return movements are tracked; quantities use thousandths. `ProgressTab` maintains phase tasks; `ContactsTab` maintains project contacts and supplier synchronization; `CalendarTab` maintains dated events. `CompletedProjectsTab` and completion dialogs expose preserved project history. None should be mistaken for automatic purchase-payment integration unless the specific code path demonstrates it.

## Authorization, persistence and recovery

Registered heads are shared people; `project_heads` are project links. PINs use salted hashes. `_pin_required_for_action` selects certain high-risk workflows by action wording; not every confirmation requests a PIN. There is no comprehensive application login/role engine or database encryption demonstrated by this architecture.

SQLite connections enable foreign keys and WAL. Some methods use `with self.conn` for atomic multi-record operations; `execute` commits independently. Some UI methods execute SQL directly, so this is not a fully isolated service/repository architecture. There is no centralized versioned migration framework: `_create_schema`, `_ensure_column`, normalizers, metadata markers and guarded repair methods perform evolution at startup. See [DATABASE](DATABASE.md) before inspecting or upgrading data.

Startup snapshots, migration backups and user backup/export actions coexist. Backups are private and may accumulate; do not treat them as source. Text exports and PDF reports are not interchangeable with a transaction-safe SQLite backup.

## Testing and maintenance limits

The current source passed 184 discovered tests on 2026-10-07. Fixtures cover payroll, split-site attendance, attendance-workbook round trips, source attribution, imports, reports, reviewed migration guards and allocation reactivation; coverage is not proof of every UI/layout or installer path. GUI tests need Tk. Executable packaging/security checks are a distinct release task.

Technical debt: monolithic source and direct SQL in UI; shadowed legacy classes; label-dependent presentation patches; JSON payloads and string method/status conventions; inconsistent declared foreign keys across upgraded databases; client-specific historical guards; no formal general-ledger accounting. Repository migration and further decomposition are **proposed—not implemented**. Maintain behavior and data provenance before refactoring.
