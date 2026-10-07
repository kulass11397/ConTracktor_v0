# Employees

Implemented reference: current `app.py` working tree based on `a329efc`; inspected 2026-10-07. Read [architecture](../ARCHITECTURE.md) and [database](../DATABASE.md) first.

## Purpose

Maintain a stable company employee identity while supporting work, rates and history across multiple projects.

## Current implementation

The active (later) `PayrollTab` provides roster, profile, archive, deployment, transfer and reactivation controls. New/reviewed references use MONCON numbering. `_migrate_company_employee_numbers` normalizes references without replacing employee IDs, keeps previous aliases and takes a backup when normalization is needed. `employees.project_id` remains a home/current profile project for compatibility; it is not the authoritative work site of every attendance row.

`deploy_employee` adds an effective assignment without duplicating/transferring the person. `transfer_employee` changes the profile/project deployment context while retaining prior work history. `employee_daily_rate_at` selects a project/date-valid assignment rate, otherwise `employee_daily_rate` uses the employee fallback. Archiving deactivates future use without removing the person's history.

## Relevant files/classes/functions

- `app.py`: active `PayrollTab`; `EmployeeEditorDialog`, `EmployeeProfileDialog`, `DeployExistingEmployeeDialog`.
- `Database`: `_migrate_company_employee_numbers`, `employee_for_clock`, `employees_deployed_to`, `employee_deployments`, `deploy_employee`, `transfer_employee`, `archive_employee`, `reactivate_employee`, `employee_daily_rate_at`.
- `app_clean.py`: `_clean_payroll` reorganizes controls, not identity/rate rules.

## Database tables and relationships

`employees` holds identity, hashed PIN, profile/project reference, pay fields, active/archive fields and optional photo BLOB. `employee_reference_history` stores former references and original project IDs. `employee_project_assignments` relates employees to projects with effective dates, position, rate and authorizing head. `attendance`, `cash_advances`, payroll plans/snapshots/adjustments and inventory borrowing reference the same employee ID.

## Important business rules

- Manual company batch attendance and advances remain independent of the top-level project. In the weekly batch-attendance grid and its generated workbook, each project tab initially lists employees deployed during the selected week, then permits any other active company employee to be shown through a dropdown. Workbook import resolves employees by active MONCON number. Adding a dropdown employee in either workflow does not create a deployment, and attendance entry still does not require prior deployment.
- Kiosk/project deployment lookup is a separate path; do not remove its checks based on manual-batch behavior.
- Project-effective daily rate wins; legacy hourly fallback is converted to an eight-hour daily equivalent when needed.
- Deployment requires an active employee, active destination, positive rate and valid confirming destination head; duplicate open assignments are rejected.
- Keep historical aliases distinct from new employee identities. Do not create another employee to represent another work site.

## Inputs and outputs

Inputs: profile/pay fields, optional photo, PIN, deployment/project/date/rate, and authorization/reason for lifecycle operations. Outputs: profile/assignment updates, preserved references, audit entries and roster/profile views. These operations do not themselves post wages or advances.

## Dependencies on other modules

Projects supply assignment destinations and heads. Attendance resolves work rates. Payroll and CAs aggregate by stable identity. Inventory identifies tool borrowers.

## Workflow example

Deploy one existing employee to a second active project with an effective rate. Keep the same employee ID/reference; record the actual site on attendance rather than creating a duplicate employee.

## Known limitations or technical debt

Employee management largely lives in the payroll UI. Company identity is layered over legacy project-scoped schema/unique constraints. Alias matching and fallback project logic require care during migration. Images/profile data are private. No separate HR permission or payroll-tax subsystem is implied.

## Important invariants and tests

Preserve employee primary keys, attendance ownership and old-reference lookup; never reset history on transfer/archive. Do not derive work cost solely from `employees.project_id`. Rate edits must not silently rewrite committed payroll snapshots. Relevant coverage: `test_company_payroll.py`, `test_company_batches.py`, and transfer/deployment/correction cases in `test_app.py`.

Historical discrepancy: `CROSS_PROJECT_WORKFLOW.md` says deployment is required before batch attendance; current manual batch code and `MONCON_PAYROLL_WORKFLOW.md` do not require it.
