# Database schema and data ownership

Inspected against application commit `a329efc`, 2026-10-07. Schema catalog extracted from a new disposable database initialized by the current code. The working database's structure was inspected read-only; no client rows are included.

## Safety and database selection

The laptop launcher selects `contractor_tracker_preview_135800.db` beside the authoritative preview source, unless `CONTRACTOR_LAUNCH_DB_PATH` overrides it. Core `resolve_db_path` also accepts `CONTRACTOR_DB_PATH` and searches nearby known filenames. Explicit selection matters: an absent file may create a new empty system.

Do not instantiate `Database` on client data for read-only inspection. Its constructor creates migration backups, opens SQLite with foreign keys/WAL, creates/adds schema, backfills/normalizes records, runs guarded historical repairs, normalizes employee numbers and repairs stale allocation status. Use SQLite read-only mode for diagnostics and temporary copies for upgrade testing. SQLite backup API captures WAL-backed transactions; copying only an open .db file is not a safe substitute.

Private databases, sidecars, snapshots, profiles and financial records stay local. This document contains structure, not a deployable client dataset.

## Current schema versus retained history

- Current code creates **50 application tables**. The inspected working database has those columns plus **one retained historical table**, `migration_bank_statement_entries` (51 tables total).
- All current application column names were present in the inspected working database. Column order, declared FKs and constraints may differ across upgraded files. This is not permission to rebuild tables or remove legacy fields.
- `migration_bank_statement_entries` is not created or used by the current core source inspected here. Its original importing tool is not established by this code; preserve it as historical staging evidence.
- Some references were added through `ALTER TABLE ADD COLUMN ... INTEGER` without FK declarations. A similarly named `*_id` is a logical relationship, not proof that SQLite enforces it.
- This is not a general-ledger schema: no complete journal/accounts, tax engine, invoice receivable or automatic fee-income subsystem is defined.

## Data conventions

Money is integer centavos (`*_cents`); Decimal/ROUND_HALF_UP conversion is in `cents`. Negative adjustments are supported where specified; most payment/source amounts have positivity checks. Inventory quantity uses integer thousandths (`*_milli`). Attendance hours and quantities may be text; snapshots also use REAL hour summaries. Dates are ISO-style text; timestamps mix application local time and SQLite defaults. Empty string often means no end/time/reference; NULL often means no optional link.

PINs are salted hashes (`pin_salt`, `pin_hash`), not plaintext passwords. Photos can be SQLite BLOBs with filename/MIME metadata. JSON fields store drafts, frozen project-gross values or metadata. Their content shape is application-enforced; SQLite does not validate every payload.

Flags/states are not uniform: expenses have `voided`, payments have `accounting_excluded`, CA transactions have `posted` and `voided`, payroll has Committed/Reopened/Superseded status, and employees have active/archive state. Apply the correct predicate for each calculation; never equate a retained row with active financial effect.

## Ownership and relationship map

```text
projects -> phases -> tasks
projects -> expenses -> payments -> ordinary project_funding_loans
employees -> attendance -> payroll_batches -> expenses
employees -> cash_advances -> cash_advance_transactions
employees -> payroll_week_plans -> payroll_week_ca_shares
                                    -> CA-recovery project_funding_loans
project_funding_loans -> project_funding_repayments
remittances (withdrawal OR physical receipt)
  -> cash_allocation_sources -> cash_allocations -> allocation activity
  -> cash_receipt_placements (pool/bank)
allocation return -> cash_pool_return_sources
surrender -> cash_redeposit_sources -> cash_redeposits -> bank_accounts
head_registry -> project_heads -> project authorizations
```

Expense project owns cost. Payment funding project owns funding. Attendance work project owns wages; employee profile project is compatibility context. Advance project owns the initial funding/receivable until recovery attribution. Cash allocation project is custody/account owner. Receipt-derived RCA accounts are computed from placements and repayment ownership; there is no independent RCA table.

## Historical-data and correction behavior

Schema evolution lives in `Database._create_schema`, `_ensure_column` and startup methods, not an external ordered migration directory. `app_metadata` stores once-only markers and fingerprints. Constructor backups precede selected migration families; clean UI also creates startup snapshots. Backup creation is not a blanket guarantee that every direct SQL operation is reversible.

Implemented compatibility families include shared-cash references/head registry; daily-rate and attendance fields; cash recovery/surrender records; older future-advance deduction correction; reviewed withdrawal source trails; reviewed Grace week-one records and duplicate bank deposit; physical receipt placement backfill; guarded live-cash opening boundary; company employee aliases; Personal phase; and positive-balance Completed/Fully Used allocation reactivation. Named client repairs have specific guards and status outcomes, and must not be generalized to other data.

Normalizers also derive expense payment status, initialize categories/rates, preserve payroll snapshots and synchronize supplier contacts. Opening the same database may therefore change labels/history metadata even when no user form is submitted. Some guards block rather than guess on changed historical fingerprints.

Historical expenses before an established cash-source boundary can remain project-reportable without replaying into today's company allocable cash. Project-filtered cash does not apply that company-wide opening boundary; do not assume project balances sum as a partition of reconciled historical company cash.

Reopening payroll keeps original batches, expenses, payments and snapshots but removes their active effects through exclusions/void/status links; replacements preserve supersession. Ordinary expense void leaves payment history but excludes it through the expense predicate. Uncommitted attendance deletion is physical deletion with an audit summary (and FK-dependent child behavior), not a universal soft-delete policy. Do not delete projects/employees because some FKs technically allow cascading deletion.

## Logical references requiring application checks

Examples include upgraded `attendance.project_id/payroll_batch_id/closure_batch_id`, payment/allocation authorization/source IDs, expense default allocation/batch/supersession fields, project-head registry links, remittance bank/fee/authorization fields, payroll replacement fields and repayment source fields. Consult each table's declared FK list below and the actual write method. Adding an FK later requires compatibility/integrity review, not a documentation-only edit.

## Indexes, constraints and triggers

The catalog below lists actual indexes, declared FK deletion behavior, primary keys and CHECK/UNIQUE constraints from current initialization. Auto-index names implement PK/UNIQUE constraints. Nullable rowid primary-key fields may report `notnull=0` through PRAGMA; that does not mean row identity is optional after insertion.

Four supplier triggers update/reactivate/create project Supplier contacts after expense or Direct Procurement supplier inserts/edits. Expense guards exclude payroll/employee-advance payees from vendor creation; historical vendor rows are also backfilled. These are persistence side effects beyond financial posting. There are no triggers implementing the full accounting invariants: many protections exist in application code.

## Table catalog

- [`app_metadata`](#app_metadata) — Application configuration and repeat-safe migration/receipt-classification markers; company/global or reference-scoped JSON/text.
- [`attendance`](#attendance) — Employee work segments and calculated pay; work-project ownership, closure and payroll links.
- [`attendance_closure_batches`](#attendance_closure_batches) — Authorized project-day closure totals and reference.
- [`attendance_revisions`](#attendance_revisions) — Attendance correction history with before/after times, pay, rates and work projects.
- [`audit_log`](#audit_log) — Operation history; optional project context is informational and has no declared FK.
- [`bank_account_transfers`](#bank_account_transfers) — Company bank-to-bank movements, not additional project funding.
- [`bank_accounts`](#bank_accounts) — Company bank account identity, details and active flag; private operational data.
- [`calendar_events`](#calendar_events) — Project calendar events and completion flags.
- [`cash_advance_batches`](#cash_advance_batches) — Funding-project batch header for individual employee advances.
- [`cash_advance_transactions`](#cash_advance_transactions) — Advance issuance, scheduled/posted recovery and void history.
- [`cash_advances`](#cash_advances) — Employee advance owned initially by the funding project, linked to expense/source.
- [`cash_allocation_sources`](#cash_allocation_sources) — Exact original source contributions for PC/DP; source remittance may be withdrawal or placed physical receipt.
- [`cash_allocation_transactions`](#cash_allocation_transactions) — Allocation issuance, payment, return/surrender and redeposit-related audit activity.
- [`cash_allocations`](#cash_allocations) — Project-owned PC/DP custody, responsible people, first-source pointer and usage state.
- [`cash_pool_return_sources`](#cash_pool_return_sources) — Exact source contributions released by a return-to-pool transaction.
- [`cash_receipt_placements`](#cash_receipt_placements) — Authorized pending physical receipt placement into project cash pool or bank.
- [`cash_redeposit_sources`](#cash_redeposit_sources) — Surrendered allocation/source contributions included in a bank redeposit.
- [`cash_redeposits`](#cash_redeposits) — Physical surrender/recovery cash deposited to bank; not new client funding.
- [`cash_repayment_surrenders`](#cash_repayment_surrenders) — Physical CA recovery held pending bank deposit, with recovery/source links.
- [`contacts`](#contacts) — Project contacts; supplier triggers can create/reactivate supplier entries.
- [`employee_project_assignments`](#employee_project_assignments) — Employee deployment, effective dates, position and project daily rate.
- [`employee_reference_history`](#employee_reference_history) — Former employee references preserved against stable identity.
- [`employees`](#employees) — Company identity/profile, compatibility home project, hashed PIN and pay fallback.
- [`expense_batches`](#expense_batches) — Project-specific committed bulk expense groups.
- [`expense_categories`](#expense_categories) — Global expense category names.
- [`expense_verification_approvals`](#expense_verification_approvals) — Heads approving an expense-verification batch.
- [`expense_verification_batches`](#expense_verification_batches) — Project verification header, date/time and reference.
- [`expense_verification_items`](#expense_verification_items) — Expenses included in a verification batch.
- [`expenses`](#expenses) — Project cost ownership and line-item commitment; payment/funding/classification/workflow hints.
- [`head_registry`](#head_registry) — Shared responsible-person identity and hashed PIN.
- [`inventory_items`](#inventory_items) — Project consumables/tools with registration quantity, unit and thresholds.
- [`inventory_transactions`](#inventory_transactions) — Opening/restock/use/borrow/return movements, borrowers and corrections.
- [`payments`](#payments) — Actual supplier/employee expense payments with funding project/source and exclusion history.
- [`payroll_adjustments`](#payroll_adjustments) — Pending/applied employee-project correction amounts with originating record links.
- [`payroll_batch_attendance_snapshots`](#payroll_batch_attendance_snapshots) — Frozen attendance detail for a committed/reopened payroll batch.
- [`payroll_batch_employee_snapshots`](#payroll_batch_employee_snapshots) — Frozen employee-week earnings/deduction/adjustment summary.
- [`payroll_batches`](#payroll_batches) — Project weekly payroll, net expense, authorization and reopen/replacement chain.
- [`payroll_week_ca_shares`](#payroll_week_ca_shares) — Exact project shares of a scheduled advance recovery within a locked employee week.
- [`payroll_week_plans`](#payroll_week_plans) — One locked employee-week attendance signature and gross-by-project JSON.
- [`phases`](#phases) — Project phases with display order; includes seeded Personal.
- [`project_completion_snapshots`](#project_completion_snapshots) — Preserved project closeout figures and reactivation history.
- [`project_funding_loans`](#project_funding_loans) — One expense-payment or CA-recovery borrowing link between distinct projects.
- [`project_funding_repayments`](#project_funding_repayments) — Loan repayments, source metadata, authorization and reversal/batch references.
- [`project_heads`](#project_heads) — Project membership/link of a registered responsible person, with compatibility PIN fields.
- [`projects`](#projects) — Client/project identity, contract spending limit and lifecycle state.
- [`remittances`](#remittances) — Project deposits/physical receipts and shared bank withdrawals; source-ledger roots.
- [`tasks`](#tasks) — Phase tasks/milestones and completion/deadline state.
- [`weekly_attendance_drafts`](#weekly_attendance_drafts) — Employee/date/project Present/Absent staging with JSON work segments.
- [`weekly_attendance_marks`](#weekly_attendance_marks) — Finalized employee/date/project absence markers; no wages.
- [`workflow_drafts`](#workflow_drafts) — Persisted expense/advance JSON drafts; do not post costs or consume sources.

## Current table details

### app_metadata

Application configuration and repeat-safe migration/receipt-classification markers; company/global or reference-scoped JSON/text.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `key` | TEXT | — | — | 1 |
| `value` | TEXT | NOT NULL | `''` | — |
| `updated_at` | TEXT | NOT NULL | `''` | — |

Declared foreign keys: none.

Indexes: `sqlite_autoindex_app_metadata_1` (UNIQUE; columns: `key`)

### attendance

Employee work segments and calculated pay; work-project ownership, closure and payroll links.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `employee_id` | INTEGER | NOT NULL | — | — |
| `clock_in` | TEXT | NOT NULL | — | — |
| `clock_out` | TEXT | NOT NULL | `''` | — |
| `hours` | TEXT | NOT NULL | `''` | — |
| `gross_cents` | INTEGER | NOT NULL | `0` | — |
| `pay_rate_cents` | INTEGER | NOT NULL | `0` | — |
| `manual_pay_adjustment_cents` | INTEGER | NOT NULL | `0` | — |
| `pay_override_note` | TEXT | NOT NULL | `''` | — |
| `committed_expense_id` | INTEGER | — | — | — |
| `regular_hours` | TEXT | NOT NULL | `''` | — |
| `lunch_hours` | TEXT | NOT NULL | `''` | — |
| `overtime_hours` | TEXT | NOT NULL | `''` | — |
| `regular_pay_cents` | INTEGER | NOT NULL | `0` | — |
| `overtime_pay_cents` | INTEGER | NOT NULL | `0` | — |
| `day_type` | TEXT | NOT NULL | `'Ordinary Day'` | — |
| `source` | TEXT | NOT NULL | `'Kiosk'` | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `payroll_batch_id` | INTEGER | — | — | — |
| `closure_batch_id` | INTEGER | — | — | — |
| `project_id` | INTEGER | — | — | — |
| `revision_count` | INTEGER | NOT NULL | `0` | — |
| `reopened_from_payroll_batch_id` | INTEGER | — | — | — |

Declared foreign keys: `committed_expense_id` → `expenses.id` (ON DELETE SET NULL); `employee_id` → `employees.id` (ON DELETE CASCADE)

Indexes: `idx_attendance_project_date` (columns: `project_id`, `clock_in`); `idx_attendance_employee` (columns: `employee_id`, `clock_in`)

### attendance_closure_batches

Authorized project-day closure totals and reference.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `closure_ref` | TEXT | NOT NULL | — | — |
| `work_date` | TEXT | NOT NULL | — | — |
| `attendance_count` | INTEGER | NOT NULL | `0` | — |
| `gross_cents` | INTEGER | NOT NULL | `0` | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `idx_attendance_closure_project` (columns: `project_id`, `work_date`); `sqlite_autoindex_attendance_closure_batches_1` (UNIQUE; columns: `closure_ref`)

### attendance_revisions

Attendance correction history with before/after times, pay, rates and work projects.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `attendance_id` | INTEGER | NOT NULL | — | — |
| `project_id` | INTEGER | NOT NULL | — | — |
| `old_clock_in` | TEXT | NOT NULL | — | — |
| `old_clock_out` | TEXT | NOT NULL | — | — |
| `new_clock_in` | TEXT | NOT NULL | — | — |
| `new_clock_out` | TEXT | NOT NULL | — | — |
| `old_gross_cents` | INTEGER | NOT NULL | `0` | — |
| `new_gross_cents` | INTEGER | NOT NULL | `0` | — |
| `old_pay_rate_cents` | INTEGER | NOT NULL | `0` | — |
| `new_pay_rate_cents` | INTEGER | NOT NULL | `0` | — |
| `old_manual_adjustment_cents` | INTEGER | NOT NULL | `0` | — |
| `new_manual_adjustment_cents` | INTEGER | NOT NULL | `0` | — |
| `payroll_batch_id` | INTEGER | — | — | — |
| `correction_reason` | TEXT | NOT NULL | — | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `old_project_id` | INTEGER | — | — | — |
| `new_project_id` | INTEGER | — | — | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `payroll_batch_id` → `payroll_batches.id` (ON DELETE SET NULL); `project_id` → `projects.id` (ON DELETE CASCADE); `attendance_id` → `attendance.id` (ON DELETE CASCADE)

Indexes: `idx_attendance_revision_record` (columns: `attendance_id`, `created_at`)

### audit_log

Operation history; optional project context is informational and has no declared FK.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | — | — | — |
| `action` | TEXT | NOT NULL | — | — |
| `details` | TEXT | NOT NULL | `''` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: none.

Indexes: none listed.

### bank_account_transfers

Company bank-to-bank movements, not additional project funding.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `reference` | TEXT | NOT NULL | — | — |
| `from_bank_account_id` | INTEGER | NOT NULL | — | — |
| `to_bank_account_id` | INTEGER | NOT NULL | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `transfer_date` | TEXT | NOT NULL | — | — |
| `transaction_time` | TEXT | NOT NULL | `''` | — |
| `purpose` | TEXT | NOT NULL | `''` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `authorized_by_registry_id` | INTEGER | — | — | — |
| `voided` | INTEGER | NOT NULL | `0` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `authorized_by_registry_id` → `head_registry.id` (ON DELETE NO ACTION); `to_bank_account_id` → `bank_accounts.id` (ON DELETE NO ACTION); `from_bank_account_id` → `bank_accounts.id` (ON DELETE NO ACTION)

Indexes: `idx_bank_transfer_destination` (columns: `to_bank_account_id`, `transfer_date`); `idx_bank_transfer_source` (columns: `from_bank_account_id`, `transfer_date`); `sqlite_autoindex_bank_account_transfers_1` (UNIQUE; columns: `reference`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(amount_cents > 0)`; `CHECK(from_bank_account_id <> to_bank_account_id)`.

### bank_accounts

Company bank account identity, details and active flag; private operational data.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `bank_name` | TEXT | NOT NULL | — | — |
| `account_name` | TEXT | NOT NULL | `''` | — |
| `account_number` | TEXT | NOT NULL | `''` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `active` | INTEGER | NOT NULL | `1` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: none.

Indexes: `sqlite_autoindex_bank_accounts_1` (UNIQUE; columns: `bank_name`, `account_number`)

Additional CHECK/composite UNIQUE/PK declarations: `UNIQUE(bank_name, account_number)`.

### calendar_events

Project calendar events and completion flags.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `type` | TEXT | NOT NULL | — | — |
| `title` | TEXT | NOT NULL | — | — |
| `event_date` | TEXT | NOT NULL | — | — |
| `event_time` | TEXT | NOT NULL | `''` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `completed` | INTEGER | NOT NULL | `0` | — |

Declared foreign keys: `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `idx_events_project_date` (columns: `project_id`, `event_date`)

### cash_advance_batches

Funding-project batch header for individual employee advances.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `batch_ref` | TEXT | NOT NULL | — | — |
| `advance_date` | TEXT | NOT NULL | — | — |
| `funding_method` | TEXT | NOT NULL | — | — |
| `bank_account_id` | INTEGER | — | — | — |
| `cash_allocation_id` | INTEGER | — | — | — |
| `total_cents` | INTEGER | NOT NULL | — | — |
| `entry_count` | INTEGER | NOT NULL | `0` | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `recorded_at_local` | TEXT | NOT NULL | — | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `cash_allocation_id` → `cash_allocations.id` (ON DELETE NO ACTION); `bank_account_id` → `bank_accounts.id` (ON DELETE NO ACTION); `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `sqlite_autoindex_cash_advance_batches_1` (UNIQUE; columns: `batch_ref`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(total_cents > 0)`.

### cash_advance_transactions

Advance issuance, scheduled/posted recovery and void history.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `advance_id` | INTEGER | NOT NULL | — | — |
| `txn_type` | TEXT | NOT NULL | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `txn_date` | TEXT | NOT NULL | — | — |
| `method` | TEXT | NOT NULL | `''` | — |
| `bank_account_id` | INTEGER | — | — | — |
| `payroll_batch_id` | INTEGER | — | — | — |
| `reference` | TEXT | NOT NULL | `''` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `posted` | INTEGER | NOT NULL | `1` | — |
| `voided` | INTEGER | NOT NULL | `0` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `recorded_at_local` | TEXT | NOT NULL | `''` | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `payroll_batch_id` → `payroll_batches.id` (ON DELETE SET NULL); `bank_account_id` → `bank_accounts.id` (ON DELETE NO ACTION); `advance_id` → `cash_advances.id` (ON DELETE CASCADE)

Indexes: `idx_cash_advance_txn` (columns: `advance_id`, `txn_date`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(amount_cents > 0)`.

### cash_advances

Employee advance owned initially by the funding project, linked to expense/source.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `employee_id` | INTEGER | NOT NULL | — | — |
| `expense_id` | INTEGER | — | — | — |
| `original_cents` | INTEGER | NOT NULL | — | — |
| `advance_date` | TEXT | NOT NULL | — | — |
| `reason` | TEXT | NOT NULL | `''` | — |
| `method` | TEXT | NOT NULL | `'Cash'` | — |
| `bank_account_id` | INTEGER | — | — | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `voided` | INTEGER | NOT NULL | `0` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `cash_allocation_id` | INTEGER | — | — | — |
| `repayment_plan` | TEXT | NOT NULL | `'Manual / Mixed'` | — |
| `weekly_deduction_cap_cents` | INTEGER | NOT NULL | `0` | — |
| `batch_id` | INTEGER | — | — | — |
| `system_reference` | TEXT | NOT NULL | `''` | — |
| `recorded_at_local` | TEXT | NOT NULL | `''` | — |
| `voided_at` | TEXT | NOT NULL | `''` | — |
| `void_reason` | TEXT | NOT NULL | `''` | — |
| `voided_by_head_id` | INTEGER | — | — | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `bank_account_id` → `bank_accounts.id` (ON DELETE NO ACTION); `expense_id` → `expenses.id` (ON DELETE SET NULL); `employee_id` → `employees.id` (ON DELETE CASCADE); `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `idx_cash_advance_system_reference` (UNIQUE; columns: `system_reference`; partial predicate: `system_reference<>''`); `idx_cash_advance_batch` (columns: `batch_id`); `idx_cash_advance_employee` (columns: `employee_id`, `advance_date`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(original_cents > 0)`.

### cash_allocation_sources

Exact original source contributions for PC/DP; source remittance may be withdrawal or placed physical receipt.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `allocation_id` | INTEGER | NOT NULL | — | 1 |
| `withdrawal_id` | INTEGER | NOT NULL | — | 2 |
| `amount_cents` | INTEGER | NOT NULL | — | — |

Declared foreign keys: `withdrawal_id` → `remittances.id` (ON DELETE NO ACTION); `allocation_id` → `cash_allocations.id` (ON DELETE CASCADE)

Indexes: `idx_cash_alloc_source_withdrawal` (columns: `withdrawal_id`); `sqlite_autoindex_cash_allocation_sources_1` (UNIQUE; columns: `allocation_id`, `withdrawal_id`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(amount_cents > 0)`; `PRIMARY KEY(allocation_id,withdrawal_id)`.

### cash_allocation_transactions

Allocation issuance, payment, return/surrender and redeposit-related audit activity.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `allocation_id` | INTEGER | NOT NULL | — | — |
| `txn_type` | TEXT | NOT NULL | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `txn_date` | TEXT | NOT NULL | — | — |
| `expense_id` | INTEGER | — | — | — |
| `payment_id` | INTEGER | — | — | — |
| `actor_head_id` | INTEGER | — | — | — |
| `counterparty_head_id` | INTEGER | — | — | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `voided` | INTEGER | NOT NULL | `0` | — |
| `voided_at` | TEXT | NOT NULL | `''` | — |
| `void_reason` | TEXT | NOT NULL | `''` | — |
| `voided_by_head_id` | INTEGER | — | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `system_reference` | TEXT | NOT NULL | `''` | — |
| `transaction_time` | TEXT | NOT NULL | `''` | — |

Declared foreign keys: `voided_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `counterparty_head_id` → `project_heads.id` (ON DELETE NO ACTION); `actor_head_id` → `project_heads.id` (ON DELETE NO ACTION); `payment_id` → `payments.id` (ON DELETE SET NULL); `expense_id` → `expenses.id` (ON DELETE SET NULL); `allocation_id` → `cash_allocations.id` (ON DELETE CASCADE)

Indexes: `idx_cash_alloc_txn` (columns: `allocation_id`, `txn_date`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(amount_cents >= 0)`.

### cash_allocations

Project-owned PC/DP custody, responsible people, first-source pointer and usage state.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `reference` | TEXT | NOT NULL | — | — |
| `withdrawal_id` | INTEGER | NOT NULL | — | — |
| `project_id` | INTEGER | NOT NULL | — | — |
| `allocation_type` | TEXT | NOT NULL | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `allocation_date` | TEXT | NOT NULL | — | — |
| `custodian_head_id` | INTEGER | — | — | — |
| `responsible_head_id` | INTEGER | — | — | — |
| `supplier` | TEXT | NOT NULL | `''` | — |
| `purpose` | TEXT | NOT NULL | `''` | — |
| `issuer_head_id` | INTEGER | NOT NULL | — | — |
| `receiver_head_id` | INTEGER | NOT NULL | — | — |
| `status` | TEXT | NOT NULL | `'Active'` | — |
| `accepted_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `closed_at` | TEXT | NOT NULL | `''` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `voided` | INTEGER | NOT NULL | `0` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `shared_scope` | INTEGER | NOT NULL | `1` | — |
| `allocation_time` | TEXT | NOT NULL | `''` | — |
| `issuer_registry_id` | INTEGER | — | — | — |
| `receiver_registry_id` | INTEGER | — | — | — |
| `source_selection_mode` | TEXT | NOT NULL | `''` | — |

Declared foreign keys: `receiver_head_id` → `project_heads.id` (ON DELETE NO ACTION); `issuer_head_id` → `project_heads.id` (ON DELETE NO ACTION); `responsible_head_id` → `project_heads.id` (ON DELETE NO ACTION); `custodian_head_id` → `project_heads.id` (ON DELETE NO ACTION); `project_id` → `projects.id` (ON DELETE CASCADE); `withdrawal_id` → `remittances.id` (ON DELETE NO ACTION)

Indexes: `idx_cash_alloc_project` (columns: `project_id`, `status`); `idx_cash_alloc_withdrawal` (columns: `withdrawal_id`); `sqlite_autoindex_cash_allocations_1` (UNIQUE; columns: `reference`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(allocation_type IN ('Petty Cash','Direct Procurement'))`; `CHECK(amount_cents > 0)`.

### cash_pool_return_sources

Exact source contributions released by a return-to-pool transaction.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `transaction_id` | INTEGER | NOT NULL | — | 1 |
| `withdrawal_id` | INTEGER | NOT NULL | — | 2 |
| `amount_cents` | INTEGER | NOT NULL | — | — |

Declared foreign keys: `withdrawal_id` → `remittances.id` (ON DELETE NO ACTION); `transaction_id` → `cash_allocation_transactions.id` (ON DELETE CASCADE)

Indexes: `idx_cash_pool_return_source_withdrawal` (columns: `withdrawal_id`); `sqlite_autoindex_cash_pool_return_sources_1` (UNIQUE; columns: `transaction_id`, `withdrawal_id`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(amount_cents > 0)`; `PRIMARY KEY(transaction_id,withdrawal_id)`.

### cash_receipt_placements

Authorized pending physical receipt placement into project cash pool or bank.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `receipt_id` | INTEGER | NOT NULL | — | — |
| `project_id` | INTEGER | NOT NULL | — | — |
| `placement_type` | TEXT | NOT NULL | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `placement_date` | TEXT | NOT NULL | — | — |
| `bank_account_id` | INTEGER | — | — | — |
| `system_reference` | TEXT | NOT NULL | — | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `voided` | INTEGER | NOT NULL | `0` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `bank_account_id` → `bank_accounts.id` (ON DELETE NO ACTION); `project_id` → `projects.id` (ON DELETE NO ACTION); `receipt_id` → `remittances.id` (ON DELETE NO ACTION)

Indexes: `idx_cash_receipt_placement_bank` (columns: `bank_account_id`, `voided`, `placement_date`); `idx_cash_receipt_placement_receipt` (columns: `receipt_id`, `voided`, `placement_date`); `sqlite_autoindex_cash_receipt_placements_1` (UNIQUE; columns: `system_reference`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK( placement_type IN ('Project Cash Pool','Bank Deposit') )`; `CHECK(amount_cents>0)`; `CHECK((placement_type='Bank Deposit' AND bank_account_id IS NOT NULL) OR (placement_type='Project Cash Pool' AND bank_account_id IS NULL))`.

### cash_redeposit_sources

Surrendered allocation/source contributions included in a bank redeposit.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `redeposit_id` | INTEGER | NOT NULL | — | 1 |
| `allocation_id` | INTEGER | NOT NULL | — | 2 |
| `withdrawal_id` | INTEGER | NOT NULL | — | 3 |
| `amount_cents` | INTEGER | NOT NULL | — | — |

Declared foreign keys: `withdrawal_id` → `remittances.id` (ON DELETE NO ACTION); `allocation_id` → `cash_allocations.id` (ON DELETE NO ACTION); `redeposit_id` → `cash_redeposits.id` (ON DELETE CASCADE)

Indexes: `idx_cash_redeposit_source_withdrawal` (columns: `withdrawal_id`); `sqlite_autoindex_cash_redeposit_sources_1` (UNIQUE; columns: `redeposit_id`, `allocation_id`, `withdrawal_id`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(amount_cents > 0)`; `PRIMARY KEY(redeposit_id,allocation_id,withdrawal_id)`.

### cash_redeposits

Physical surrender/recovery cash deposited to bank; not new client funding.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `reference` | TEXT | NOT NULL | — | — |
| `bank_account_id` | INTEGER | NOT NULL | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `deposit_date` | TEXT | NOT NULL | — | — |
| `transaction_time` | TEXT | NOT NULL | — | — |
| `authorized_by_registry_id` | INTEGER | — | — | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `voided` | INTEGER | NOT NULL | `0` | — |
| `voided_at` | TEXT | NOT NULL | `''` | — |
| `void_reason` | TEXT | NOT NULL | `''` | — |
| `voided_by_registry_id` | INTEGER | — | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `voided_by_registry_id` → `head_registry.id` (ON DELETE NO ACTION); `authorized_by_registry_id` → `head_registry.id` (ON DELETE NO ACTION); `bank_account_id` → `bank_accounts.id` (ON DELETE NO ACTION)

Indexes: `idx_cash_redeposit_bank` (columns: `bank_account_id`, `deposit_date`); `sqlite_autoindex_cash_redeposits_1` (UNIQUE; columns: `reference`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(amount_cents > 0)`.

### cash_repayment_surrenders

Physical CA recovery held pending bank deposit, with recovery/source links.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `reference` | TEXT | NOT NULL | — | — |
| `advance_transaction_id` | INTEGER | NOT NULL | — | — |
| `advance_id` | INTEGER | NOT NULL | — | — |
| `cash_allocation_id` | INTEGER | — | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `surrender_date` | TEXT | NOT NULL | — | — |
| `transaction_time` | TEXT | NOT NULL | `''` | — |
| `received_by_head_id` | INTEGER | — | — | — |
| `status` | TEXT | NOT NULL | `'Awaiting Deposit'` | — |
| `redeposit_id` | INTEGER | — | — | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `voided_at` | TEXT | NOT NULL | `''` | — |
| `void_reason` | TEXT | NOT NULL | `''` | — |
| `voided_by_head_id` | INTEGER | — | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `voided_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `redeposit_id` → `cash_redeposits.id` (ON DELETE SET NULL); `received_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `cash_allocation_id` → `cash_allocations.id` (ON DELETE SET NULL); `advance_id` → `cash_advances.id` (ON DELETE CASCADE); `advance_transaction_id` → `cash_advance_transactions.id` (ON DELETE CASCADE)

Indexes: `idx_cash_repayment_surrender_status` (columns: `status`, `surrender_date`); `sqlite_autoindex_cash_repayment_surrenders_2` (UNIQUE; columns: `advance_transaction_id`); `sqlite_autoindex_cash_repayment_surrenders_1` (UNIQUE; columns: `reference`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(amount_cents > 0)`.

### contacts

Project contacts; supplier triggers can create/reactivate supplier entries.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `name` | TEXT | NOT NULL | — | — |
| `role` | TEXT | NOT NULL | `''` | — |
| `company` | TEXT | NOT NULL | `''` | — |
| `phone` | TEXT | NOT NULL | `''` | — |
| `email` | TEXT | NOT NULL | `''` | — |
| `address` | TEXT | NOT NULL | `''` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `active` | INTEGER | NOT NULL | `1` | — |

Declared foreign keys: `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: none listed.

### employee_project_assignments

Employee deployment, effective dates, position and project daily rate.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `employee_id` | INTEGER | NOT NULL | — | — |
| `project_id` | INTEGER | NOT NULL | — | — |
| `effective_from` | TEXT | NOT NULL | — | — |
| `effective_to` | TEXT | NOT NULL | `''` | — |
| `position` | TEXT | NOT NULL | `''` | — |
| `daily_rate_cents` | INTEGER | NOT NULL | `0` | — |
| `reason` | TEXT | NOT NULL | `''` | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `project_id` → `projects.id` (ON DELETE CASCADE); `employee_id` → `employees.id` (ON DELETE CASCADE)

Indexes: `idx_employee_active_project_assignment` (UNIQUE; columns: `employee_id`, `project_id`; partial predicate: `effective_to=''`)

### employee_reference_history

Former employee references preserved against stable identity.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `employee_id` | INTEGER | NOT NULL | — | 1 |
| `previous_reference` | TEXT | NOT NULL | — | 2 |
| `original_project_id` | INTEGER | NOT NULL | — | — |
| `changed_at` | TEXT | NOT NULL | — | — |

Declared foreign keys: `employee_id` → `employees.id` (ON DELETE NO ACTION)

Indexes: `sqlite_autoindex_employee_reference_history_1` (UNIQUE; columns: `employee_id`, `previous_reference`)

Additional CHECK/composite UNIQUE/PK declarations: `PRIMARY KEY(employee_id,previous_reference)`.

### employees

Company identity/profile, compatibility home project, hashed PIN and pay fallback.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `employee_no` | TEXT | NOT NULL | — | — |
| `pin_salt` | TEXT | NOT NULL | — | — |
| `pin_hash` | TEXT | NOT NULL | — | — |
| `name` | TEXT | NOT NULL | — | — |
| `position` | TEXT | NOT NULL | `''` | — |
| `class` | TEXT | NOT NULL | `'Labor'` | — |
| `pay_basis` | TEXT | NOT NULL | `'Daily'` | — |
| `rate_cents` | INTEGER | NOT NULL | `0` | — |
| `standard_hours` | TEXT | NOT NULL | `'8'` | — |
| `active` | INTEGER | NOT NULL | `1` | — |
| `birthday` | TEXT | NOT NULL | `''` | — |
| `contact_number` | TEXT | NOT NULL | `''` | — |
| `daily_rate_cents` | INTEGER | NOT NULL | `0` | — |
| `nbi_clearance` | INTEGER | NOT NULL | `0` | — |
| `police_clearance` | INTEGER | NOT NULL | `0` | — |
| `drug_test` | INTEGER | NOT NULL | `0` | — |
| `biodata` | INTEGER | NOT NULL | `0` | — |
| `photo_data` | BLOB | — | — | — |
| `photo_filename` | TEXT | NOT NULL | `''` | — |
| `photo_mime` | TEXT | NOT NULL | `''` | — |
| `archived_at` | TEXT | NOT NULL | `''` | — |
| `archive_reason` | TEXT | NOT NULL | `''` | — |

Declared foreign keys: `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `sqlite_autoindex_employees_1` (UNIQUE; columns: `project_id`, `employee_no`)

Additional CHECK/composite UNIQUE/PK declarations: `UNIQUE(project_id, employee_no)`.

### expense_batches

Project-specific committed bulk expense groups.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `reference` | TEXT | NOT NULL | — | — |
| `project_id` | INTEGER | NOT NULL | — | — |
| `committed_at` | TEXT | NOT NULL | — | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `notes` | TEXT | NOT NULL | `''` | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `idx_expense_batch_project` (columns: `project_id`, `committed_at`); `sqlite_autoindex_expense_batches_1` (UNIQUE; columns: `reference`)

### expense_categories

Global expense category names.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `name` | TEXT | NOT NULL | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: none.

Indexes: `sqlite_autoindex_expense_categories_1` (UNIQUE; columns: `name`)

### expense_verification_approvals

Heads approving an expense-verification batch.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `batch_id` | INTEGER | NOT NULL | — | 1 |
| `head_id` | INTEGER | NOT NULL | — | 2 |
| `approved_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `head_id` → `project_heads.id` (ON DELETE NO ACTION); `batch_id` → `expense_verification_batches.id` (ON DELETE CASCADE)

Indexes: `sqlite_autoindex_expense_verification_approvals_1` (UNIQUE; columns: `batch_id`, `head_id`)

Additional CHECK/composite UNIQUE/PK declarations: `PRIMARY KEY(batch_id, head_id)`.

### expense_verification_batches

Project verification header, date/time and reference.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `reference` | TEXT | NOT NULL | — | — |
| `project_id` | INTEGER | NOT NULL | — | — |
| `verification_date` | TEXT | NOT NULL | — | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `verification_time` | TEXT | NOT NULL | `''` | — |

Declared foreign keys: `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `sqlite_autoindex_expense_verification_batches_1` (UNIQUE; columns: `reference`)

### expense_verification_items

Expenses included in a verification batch.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `batch_id` | INTEGER | NOT NULL | — | 1 |
| `expense_id` | INTEGER | NOT NULL | — | 2 |

Declared foreign keys: `expense_id` → `expenses.id` (ON DELETE CASCADE); `batch_id` → `expense_verification_batches.id` (ON DELETE CASCADE)

Indexes: `idx_expense_verify_item` (columns: `expense_id`); `sqlite_autoindex_expense_verification_items_1` (UNIQUE; columns: `batch_id`, `expense_id`)

Additional CHECK/composite UNIQUE/PK declarations: `PRIMARY KEY(batch_id, expense_id)`.

### expenses

Project cost ownership and line-item commitment; payment/funding/classification/workflow hints.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `name` | TEXT | NOT NULL | — | — |
| `item` | TEXT | NOT NULL | `''` | — |
| `dimensions` | TEXT | NOT NULL | `''` | — |
| `supplier` | TEXT | NOT NULL | `''` | — |
| `qty` | TEXT | NOT NULL | `'1'` | — |
| `unit` | TEXT | NOT NULL | `''` | — |
| `unit_price_cents` | INTEGER | NOT NULL | `0` | — |
| `total_cents` | INTEGER | NOT NULL | `0` | — |
| `phase_id` | INTEGER | — | — | — |
| `area` | TEXT | NOT NULL | `''` | — |
| `trade` | TEXT | NOT NULL | `''` | — |
| `expense_date` | TEXT | NOT NULL | — | — |
| `due_date` | TEXT | NOT NULL | `''` | — |
| `invoice_no` | TEXT | NOT NULL | `''` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `voided` | INTEGER | NOT NULL | `0` | — |
| `payroll_batch` | TEXT | NOT NULL | `''` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `status` | TEXT | NOT NULL | `'Unpaid'` | — |
| `funding_project_id` | INTEGER | — | — | — |
| `funding_source_type` | TEXT | NOT NULL | `'Project'` | — |
| `default_cash_allocation_id` | INTEGER | — | — | — |
| `expense_batch_id` | INTEGER | — | — | — |
| `verification_status` | TEXT | NOT NULL | `'Unverified'` | — |
| `verified_at` | TEXT | NOT NULL | `''` | — |
| `workflow_status` | TEXT | NOT NULL | `''` | — |
| `superseded_by_payroll_batch_id` | INTEGER | — | — | — |

Declared foreign keys: `funding_project_id` → `projects.id` (ON DELETE NO ACTION); `phase_id` → `phases.id` (ON DELETE SET NULL); `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `idx_expenses_project` (columns: `project_id`)

### head_registry

Shared responsible-person identity and hashed PIN.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `name` | TEXT | NOT NULL | — | — |
| `position` | TEXT | NOT NULL | `''` | — |
| `pin_salt` | TEXT | NOT NULL | — | — |
| `pin_hash` | TEXT | NOT NULL | — | — |
| `active` | INTEGER | NOT NULL | `1` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: none.

Indexes: `idx_head_registry_identity` (UNIQUE; columns: `null`, `null`)

### inventory_items

Project consumables/tools with registration quantity, unit and thresholds.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `item_code` | TEXT | NOT NULL | — | — |
| `name` | TEXT | NOT NULL | — | — |
| `material_type` | TEXT | NOT NULL | — | — |
| `category` | TEXT | NOT NULL | `''` | — |
| `unit` | TEXT | NOT NULL | `'piece'` | — |
| `registered_quantity_milli` | INTEGER | NOT NULL | `0` | — |
| `reorder_level_milli` | INTEGER | NOT NULL | `0` | — |
| `condition_status` | TEXT | NOT NULL | `'Good'` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `active` | INTEGER | NOT NULL | `1` | — |
| `created_by_head_id` | INTEGER | — | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `created_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `idx_inventory_item_project` (columns: `project_id`, `material_type`, `active`); `sqlite_autoindex_inventory_items_1` (UNIQUE; columns: `item_code`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(material_type IN ('Consumable','Non-Consumable'))`.

### inventory_transactions

Opening/restock/use/borrow/return movements, borrowers and corrections.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `reference` | TEXT | NOT NULL | — | — |
| `project_id` | INTEGER | NOT NULL | — | — |
| `item_id` | INTEGER | NOT NULL | — | — |
| `employee_id` | INTEGER | — | — | — |
| `transaction_type` | TEXT | NOT NULL | — | — |
| `quantity_milli` | INTEGER | NOT NULL | — | — |
| `transaction_date` | TEXT | NOT NULL | — | — |
| `transaction_time` | TEXT | NOT NULL | `''` | — |
| `reason` | TEXT | NOT NULL | `''` | — |
| `condition_note` | TEXT | NOT NULL | `''` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `linked_transaction_id` | INTEGER | — | — | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `voided` | INTEGER | NOT NULL | `0` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `revision_count` | INTEGER | NOT NULL | `0` | — |
| `last_edited_at` | TEXT | NOT NULL | `''` | — |
| `edit_reason` | TEXT | NOT NULL | `''` | — |
| `last_edited_by_head_id` | INTEGER | — | — | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `linked_transaction_id` → `inventory_transactions.id` (ON DELETE SET NULL); `employee_id` → `employees.id` (ON DELETE SET NULL); `item_id` → `inventory_items.id` (ON DELETE CASCADE); `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `idx_inventory_transaction_employee` (columns: `employee_id`, `transaction_date`, `id`); `idx_inventory_transaction_item` (columns: `item_id`, `transaction_date`, `id`); `sqlite_autoindex_inventory_transactions_1` (UNIQUE; columns: `reference`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(quantity_milli > 0)`.

### payments

Actual supplier/employee expense payments with funding project/source and exclusion history.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `expense_id` | INTEGER | NOT NULL | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `payment_date` | TEXT | NOT NULL | — | — |
| `method` | TEXT | NOT NULL | `''` | — |
| `reference` | TEXT | NOT NULL | `''` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `bank_account_id` | INTEGER | — | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `cash_allocation_id` | INTEGER | — | — | — |
| `system_reference` | TEXT | NOT NULL | `''` | — |
| `transaction_time` | TEXT | NOT NULL | `''` | — |
| `accounting_excluded` | INTEGER | NOT NULL | `0` | — |
| `funding_project_id` | INTEGER | — | — | — |
| `funding_source_type` | TEXT | NOT NULL | `'Project'` | — |

Declared foreign keys: `funding_project_id` → `projects.id` (ON DELETE NO ACTION); `bank_account_id` → `bank_accounts.id` (ON DELETE NO ACTION); `expense_id` → `expenses.id` (ON DELETE CASCADE)

Indexes: none listed.

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(amount_cents > 0)`.

### payroll_adjustments

Pending/applied employee-project correction amounts with originating record links.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `employee_id` | INTEGER | NOT NULL | — | — |
| `project_id` | INTEGER | NOT NULL | — | — |
| `source_attendance_id` | INTEGER | — | — | — |
| `source_payroll_batch_id` | INTEGER | — | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `reason` | TEXT | NOT NULL | — | — |
| `status` | TEXT | NOT NULL | `'Pending'` | — |
| `applied_payroll_batch_id` | INTEGER | — | — | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `applied_payroll_batch_id` → `payroll_batches.id` (ON DELETE SET NULL); `source_payroll_batch_id` → `payroll_batches.id` (ON DELETE SET NULL); `source_attendance_id` → `attendance.id` (ON DELETE SET NULL); `project_id` → `projects.id` (ON DELETE CASCADE); `employee_id` → `employees.id` (ON DELETE CASCADE)

Indexes: `idx_payroll_adjustment_pending` (columns: `project_id`, `status`, `employee_id`)

### payroll_batch_attendance_snapshots

Frozen attendance detail for a committed/reopened payroll batch.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `payroll_batch_id` | INTEGER | NOT NULL | — | 1 |
| `attendance_id` | INTEGER | NOT NULL | — | 2 |
| `employee_id` | INTEGER | NOT NULL | — | — |
| `employee_name` | TEXT | NOT NULL | `''` | — |
| `clock_in` | TEXT | NOT NULL | `''` | — |
| `clock_out` | TEXT | NOT NULL | `''` | — |
| `hours` | TEXT | NOT NULL | `''` | — |
| `lunch_hours` | TEXT | NOT NULL | `''` | — |
| `regular_hours` | TEXT | NOT NULL | `''` | — |
| `overtime_hours` | TEXT | NOT NULL | `''` | — |
| `regular_pay_cents` | INTEGER | NOT NULL | `0` | — |
| `overtime_pay_cents` | INTEGER | NOT NULL | `0` | — |
| `gross_cents` | INTEGER | NOT NULL | `0` | — |
| `pay_rate_cents` | INTEGER | NOT NULL | `0` | — |
| `manual_pay_adjustment_cents` | INTEGER | NOT NULL | `0` | — |
| `source` | TEXT | NOT NULL | `''` | — |
| `revision_count` | INTEGER | NOT NULL | `0` | — |

Declared foreign keys: `employee_id` → `employees.id` (ON DELETE NO ACTION); `attendance_id` → `attendance.id` (ON DELETE NO ACTION); `payroll_batch_id` → `payroll_batches.id` (ON DELETE CASCADE)

Indexes: `sqlite_autoindex_payroll_batch_attendance_snapshots_1` (UNIQUE; columns: `payroll_batch_id`, `attendance_id`)

Additional CHECK/composite UNIQUE/PK declarations: `PRIMARY KEY(payroll_batch_id,attendance_id)`.

### payroll_batch_employee_snapshots

Frozen employee-week earnings/deduction/adjustment summary.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `payroll_batch_id` | INTEGER | NOT NULL | — | 1 |
| `employee_id` | INTEGER | NOT NULL | — | 2 |
| `employee_no` | TEXT | NOT NULL | `''` | — |
| `employee_name` | TEXT | NOT NULL | `''` | — |
| `position` | TEXT | NOT NULL | `''` | — |
| `class` | TEXT | NOT NULL | `''` | — |
| `attendance_entries` | INTEGER | NOT NULL | `0` | — |
| `attendance_days` | INTEGER | NOT NULL | `0` | — |
| `regular_hours` | REAL | NOT NULL | `0` | — |
| `overtime_hours` | REAL | NOT NULL | `0` | — |
| `regular_pay_cents` | INTEGER | NOT NULL | `0` | — |
| `overtime_pay_cents` | INTEGER | NOT NULL | `0` | — |
| `gross_cents` | INTEGER | NOT NULL | `0` | — |
| `deduction_cents` | INTEGER | NOT NULL | `0` | — |
| `adjustment_cents` | INTEGER | NOT NULL | `0` | — |

Declared foreign keys: `employee_id` → `employees.id` (ON DELETE NO ACTION); `payroll_batch_id` → `payroll_batches.id` (ON DELETE CASCADE)

Indexes: `sqlite_autoindex_payroll_batch_employee_snapshots_1` (UNIQUE; columns: `payroll_batch_id`, `employee_id`)

Additional CHECK/composite UNIQUE/PK declarations: `PRIMARY KEY(payroll_batch_id,employee_id)`.

### payroll_batches

Project weekly payroll, net expense, authorization and reopen/replacement chain.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `batch_ref` | TEXT | NOT NULL | — | — |
| `period_start` | TEXT | NOT NULL | — | — |
| `period_end` | TEXT | NOT NULL | — | — |
| `gross_cents` | INTEGER | NOT NULL | `0` | — |
| `deduction_cents` | INTEGER | NOT NULL | `0` | — |
| `net_cents` | INTEGER | NOT NULL | `0` | — |
| `expense_id` | INTEGER | — | — | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `week_schedule` | TEXT | NOT NULL | `'Legacy / Stored Period'` | — |
| `adjustment_cents` | INTEGER | NOT NULL | `0` | — |
| `status` | TEXT | NOT NULL | `'Committed'` | — |
| `reopened_at` | TEXT | NOT NULL | `''` | — |
| `reopen_reason` | TEXT | NOT NULL | `''` | — |
| `reopened_by_head_id` | INTEGER | — | — | — |
| `supersedes_batch_id` | INTEGER | — | — | — |
| `replacement_batch_id` | INTEGER | — | — | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `expense_id` → `expenses.id` (ON DELETE SET NULL); `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `sqlite_autoindex_payroll_batches_1` (UNIQUE; columns: `batch_ref`)

### payroll_week_ca_shares

Exact project shares of a scheduled advance recovery within a locked employee week.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `plan_id` | INTEGER | NOT NULL | — | — |
| `project_id` | INTEGER | NOT NULL | — | — |
| `advance_id` | INTEGER | NOT NULL | — | — |
| `schedule_id` | INTEGER | NOT NULL | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `payroll_batch_id` | INTEGER | — | — | — |

Declared foreign keys: `payroll_batch_id` → `payroll_batches.id` (ON DELETE NO ACTION); `schedule_id` → `cash_advance_transactions.id` (ON DELETE NO ACTION); `advance_id` → `cash_advances.id` (ON DELETE NO ACTION); `project_id` → `projects.id` (ON DELETE NO ACTION); `plan_id` → `payroll_week_plans.id` (ON DELETE CASCADE)

Indexes: `sqlite_autoindex_payroll_week_ca_shares_1` (UNIQUE; columns: `plan_id`, `project_id`, `schedule_id`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(amount_cents>0)`; `UNIQUE(plan_id,project_id,schedule_id)`.

### payroll_week_plans

One locked employee-week attendance signature and gross-by-project JSON.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `employee_id` | INTEGER | NOT NULL | — | — |
| `period_start` | TEXT | NOT NULL | — | — |
| `period_end` | TEXT | NOT NULL | — | — |
| `attendance_signature` | TEXT | NOT NULL | — | — |
| `gross_json` | TEXT | NOT NULL | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `employee_id` → `employees.id` (ON DELETE NO ACTION)

Indexes: `sqlite_autoindex_payroll_week_plans_1` (UNIQUE; columns: `employee_id`, `period_start`)

Additional CHECK/composite UNIQUE/PK declarations: `UNIQUE(employee_id,period_start)`.

### phases

Project phases with display order; includes seeded Personal.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `name` | TEXT | NOT NULL | — | — |
| `sort_order` | INTEGER | NOT NULL | `0` | — |

Declared foreign keys: `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: none listed.

### project_completion_snapshots

Preserved project closeout figures and reactivation history.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `completion_reference` | TEXT | NOT NULL | — | — |
| `completion_date` | TEXT | NOT NULL | — | — |
| `completion_time` | TEXT | NOT NULL | `''` | — |
| `completed_by_head_ids` | TEXT | NOT NULL | `''` | — |
| `completed_by_names` | TEXT | NOT NULL | `''` | — |
| `completion_notes` | TEXT | NOT NULL | `''` | — |
| `contract_value_cents` | INTEGER | NOT NULL | `0` | — |
| `deposited_cents` | INTEGER | NOT NULL | `0` | — |
| `active_expense_cents` | INTEGER | NOT NULL | `0` | — |
| `paid_cents` | INTEGER | NOT NULL | `0` | — |
| `outstanding_cents` | INTEGER | NOT NULL | `0` | — |
| `budget_remaining_cents` | INTEGER | NOT NULL | `0` | — |
| `task_count` | INTEGER | NOT NULL | `0` | — |
| `completed_task_count` | INTEGER | NOT NULL | `0` | — |
| `progress_percent` | INTEGER | NOT NULL | `0` | — |
| `expense_count` | INTEGER | NOT NULL | `0` | — |
| `payroll_batch_count` | INTEGER | NOT NULL | `0` | — |
| `attendance_count` | INTEGER | NOT NULL | `0` | — |
| `reactivated_at` | TEXT | NOT NULL | `''` | — |
| `reactivated_by_names` | TEXT | NOT NULL | `''` | — |
| `reactivation_notes` | TEXT | NOT NULL | `''` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `idx_project_completion_project` (columns: `project_id`, `completion_date`); `sqlite_autoindex_project_completion_snapshots_1` (UNIQUE; columns: `completion_reference`)

### project_funding_loans

One expense-payment or CA-recovery borrowing link between distinct projects.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `reference` | TEXT | NOT NULL | — | — |
| `lender_project_id` | INTEGER | NOT NULL | — | — |
| `borrower_project_id` | INTEGER | NOT NULL | — | — |
| `expense_id` | INTEGER | — | — | — |
| `payment_id` | INTEGER | — | — | — |
| `ca_share_id` | INTEGER | — | — | — |
| `payroll_batch_id` | INTEGER | — | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `loan_date` | TEXT | NOT NULL | — | — |
| `kind` | TEXT | NOT NULL | `'Expense funding'` | — |
| `notes` | TEXT | NOT NULL | `''` | — |

Declared foreign keys: `payroll_batch_id` → `payroll_batches.id` (ON DELETE NO ACTION); `ca_share_id` → `payroll_week_ca_shares.id` (ON DELETE SET NULL); `payment_id` → `payments.id` (ON DELETE NO ACTION); `expense_id` → `expenses.id` (ON DELETE NO ACTION); `borrower_project_id` → `projects.id` (ON DELETE NO ACTION); `lender_project_id` → `projects.id` (ON DELETE NO ACTION)

Indexes: `sqlite_autoindex_project_funding_loans_3` (UNIQUE; columns: `ca_share_id`); `sqlite_autoindex_project_funding_loans_2` (UNIQUE; columns: `payment_id`); `sqlite_autoindex_project_funding_loans_1` (UNIQUE; columns: `reference`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(amount_cents>0)`; `CHECK(lender_project_id<>borrower_project_id)`.

### project_funding_repayments

Loan repayments, source metadata, authorization and reversal/batch references.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `loan_id` | INTEGER | NOT NULL | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `repayment_date` | TEXT | NOT NULL | — | — |
| `reference` | TEXT | NOT NULL | `''` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `voided` | INTEGER | NOT NULL | `0` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `source_type` | TEXT | NOT NULL | `'Legacy / Unspecified'` | — |
| `source_remittance_id` | INTEGER | — | — | — |
| `bank_account_id` | INTEGER | — | — | — |
| `cash_allocation_id` | INTEGER | — | — | — |
| `system_reference` | TEXT | NOT NULL | `''` | — |
| `batch_reference` | TEXT | NOT NULL | `''` | — |
| `transaction_time` | TEXT | NOT NULL | `''` | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `loan_id` → `project_funding_loans.id` (ON DELETE NO ACTION)

Indexes: none listed.

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(amount_cents>0)`.

### project_heads

Project membership/link of a registered responsible person, with compatibility PIN fields.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `name` | TEXT | NOT NULL | — | — |
| `position` | TEXT | NOT NULL | `''` | — |
| `pin_salt` | TEXT | NOT NULL | — | — |
| `pin_hash` | TEXT | NOT NULL | — | — |
| `active` | INTEGER | NOT NULL | `1` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `registry_head_id` | INTEGER | — | — | — |

Declared foreign keys: `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: none listed.

### projects

Client/project identity, contract spending limit and lifecycle state.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `name` | TEXT | NOT NULL | — | — |
| `client` | TEXT | NOT NULL | `''` | — |
| `contract_value_cents` | INTEGER | NOT NULL | `0` | — |
| `start_date` | TEXT | NOT NULL | `''` | — |
| `target_date` | TEXT | NOT NULL | `''` | — |
| `address` | TEXT | NOT NULL | `''` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `status` | TEXT | NOT NULL | `'Active'` | — |
| `completed_at` | TEXT | NOT NULL | `''` | — |
| `completion_reference` | TEXT | NOT NULL | `''` | — |
| `completion_notes` | TEXT | NOT NULL | `''` | — |
| `completed_by_names` | TEXT | NOT NULL | `''` | — |

Declared foreign keys: none.

Indexes: none listed.

### remittances

Project deposits/physical receipts and shared bank withdrawals; source-ledger roots.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | NOT NULL | — | — |
| `type` | TEXT | NOT NULL | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `withdrawal_fee_cents` | INTEGER | NOT NULL | `0` | — |
| `withdrawal_fee_expense_id` | INTEGER | — | — | — |
| `txn_date` | TEXT | NOT NULL | — | — |
| `purpose` | TEXT | NOT NULL | `''` | — |
| `care_of` | TEXT | NOT NULL | `''` | — |
| `signature` | TEXT | NOT NULL | `''` | — |
| `notes` | TEXT | NOT NULL | `''` | — |
| `voided` | INTEGER | NOT NULL | `0` | — |
| `authorized_by_head_id` | INTEGER | — | — | — |
| `authorized_by_registry_id` | INTEGER | — | — | — |
| `bank_account_id` | INTEGER | — | — | — |
| `shared_cash` | INTEGER | NOT NULL | `0` | — |
| `system_reference` | TEXT | NOT NULL | `''` | — |
| `transaction_time` | TEXT | NOT NULL | `''` | — |
| `created_at` | TEXT | NOT NULL | `''` | — |
| `cash_received` | INTEGER | NOT NULL | `0` | — |

Declared foreign keys: `withdrawal_fee_expense_id` → `expenses.id` (ON DELETE NO ACTION); `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: none listed.

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(type IN ('Deposit','Withdrawal'))`.

### tasks

Phase tasks/milestones and completion/deadline state.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `phase_id` | INTEGER | NOT NULL | — | — |
| `milestone` | TEXT | NOT NULL | `''` | — |
| `name` | TEXT | NOT NULL | — | — |
| `deadline` | TEXT | NOT NULL | `''` | — |
| `completed` | INTEGER | NOT NULL | `0` | — |
| `completed_at` | TEXT | NOT NULL | `''` | — |

Declared foreign keys: `phase_id` → `phases.id` (ON DELETE CASCADE)

Indexes: `idx_tasks_phase` (columns: `phase_id`)

### weekly_attendance_drafts

Employee/date/project Present/Absent staging with JSON work segments.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `week_start` | TEXT | NOT NULL | — | 1 |
| `employee_id` | INTEGER | NOT NULL | — | 2 |
| `work_date` | TEXT | NOT NULL | — | 3 |
| `project_id` | INTEGER | NOT NULL | — | 4 |
| `state` | TEXT | NOT NULL | — | — |
| `segments_json` | TEXT | NOT NULL | `'[]'` | — |
| `updated_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `project_id` → `projects.id` (ON DELETE NO ACTION); `employee_id` → `employees.id` (ON DELETE NO ACTION)

Indexes: `sqlite_autoindex_weekly_attendance_drafts_1` (UNIQUE; columns: `week_start`, `employee_id`, `work_date`, `project_id`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(state IN ('Present','Absent'))`; `PRIMARY KEY(week_start,employee_id,work_date,project_id)`.

### weekly_attendance_marks

Finalized employee/date/project absence markers; no wages.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `week_start` | TEXT | NOT NULL | — | 1 |
| `employee_id` | INTEGER | NOT NULL | — | 2 |
| `work_date` | TEXT | NOT NULL | — | 3 |
| `project_id` | INTEGER | NOT NULL | — | 4 |
| `state` | TEXT | NOT NULL | — | — |
| `authorized_by_head_id` | INTEGER | NOT NULL | — | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |

Declared foreign keys: `authorized_by_head_id` → `project_heads.id` (ON DELETE NO ACTION); `project_id` → `projects.id` (ON DELETE NO ACTION); `employee_id` → `employees.id` (ON DELETE NO ACTION)

Indexes: `sqlite_autoindex_weekly_attendance_marks_1` (UNIQUE; columns: `week_start`, `employee_id`, `work_date`, `project_id`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(state='Absent')`; `PRIMARY KEY(week_start,employee_id,work_date,project_id)`.

### workflow_drafts

Persisted expense/advance JSON drafts; do not post costs or consume sources.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `project_id` | INTEGER | — | — | — |
| `draft_type` | TEXT | NOT NULL | — | — |
| `reference` | TEXT | NOT NULL | — | — |
| `payload_json` | TEXT | NOT NULL | — | — |
| `status` | TEXT | NOT NULL | `'Draft'` | — |
| `created_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `updated_at` | TEXT | NOT NULL | `CURRENT_TIMESTAMP` | — |
| `committed_at` | TEXT | NOT NULL | `''` | — |

Declared foreign keys: `project_id` → `projects.id` (ON DELETE CASCADE)

Indexes: `idx_workflow_draft_project` (columns: `project_id`, `draft_type`, `status`, `updated_at`); `sqlite_autoindex_workflow_drafts_1` (UNIQUE; columns: `reference`)

Additional CHECK/composite UNIQUE/PK declarations: `CHECK(draft_type IN ('cash_advance_batch','expense_batch'))`.

## Retained historical table: migration_bank_statement_entries

Present only in the inspected working database, not created by current application initialization. Preserve locally; do not recreate or publish its rows as fixtures.

| Column | Type | Required flag | Default | PK position |
|---|---|---|---|---|
| `id` | INTEGER | — | — | 1 |
| `source_row` | INTEGER | NOT NULL | — | — |
| `direction` | TEXT | NOT NULL | — | — |
| `txn_date` | TEXT | NOT NULL | — | — |
| `amount_cents` | INTEGER | NOT NULL | — | — |
| `method` | TEXT | NOT NULL | — | — |
| `issued_by` | TEXT | NOT NULL | `''` | — |
| `remarks` | TEXT | NOT NULL | `''` | — |
| `imported_at` | TEXT | NOT NULL | — | — |

These fields describe source-row/direction/date/amount/method/issuer/remarks/import-time staging. Current source does not establish an automatic relationship between these staging rows and remittances/payments. The current application does not use them as a replacement financial ledger.

## Schema verification and maintenance

After schema changes, regenerate/check this catalog using an empty disposable database through the current `Database` class; compare private existing schema read-only. Never embed private rows, bank details, hashes or photo contents. Review declared constraints, logical references and historical compatibility separately. Relevant tests include schema/backups/partial-bank cases in `test_app.py`, reviewed repairs in `test_wd_repair.py` and project funding/payroll/source tests.

Planned repository/module restructuring is **not implemented**. A future versioned migration framework and stricter general FK coverage would require separately approved code work.
