# Projects

Implemented reference: `app.py` at `a329efc`; inspected 2026-10-07.

## Purpose

Own project costs, contract limits, client funding context, phases/tasks, responsible heads and closeout history.

## Current implementation

`ProjectsTab` is the dashboard/project management page; the application header selects a project or All Projects. Project creation seeds default phases and links heads. `_ensure_personal_phase` adds Personal to existing projects if absent, case-insensitively. Personal is not a special account type: selecting that phase does not change expense ownership automatically.

Project financial functions distinguish contract cost budgets, payment-basis balances, commitments and inter-project receivables/payables. Completion checks block open/uncommitted attendance and report other unresolved items as warnings. Completing stores a financial/process snapshot and marks the project completed; history is retained. Reactivation is an explicit authorized operation.

## Relevant files/classes/functions

`app.py`: `ProjectsTab`, `CompletedProjectsTab`, `ProjectCompletionDialog`, `CompletedProjectDetailsDialog`, `ProgressTab`, `ContractorApp.load_projects/select_project`. `Database`: `create_project`, `_ensure_personal_phase`, `assign_registered_heads`, `project_is_active`, `project_budget`, `project_commitment_budget`, `project_cost_budget`, `dashboard_financial_summary`, `project_completion_checks`, `complete_project`, `reactivate_project`. `app_clean.py` supplies Project Actions/header layout.

## Database tables and relationships

`projects` owns contract/client/address/status fields. `phases` and `tasks` support progress. `head_registry` stores people; `project_heads` links them to projects. `project_completion_snapshots` retains closeout values and reactivation notes. Expenses, remittances, assignments, loans, cash allocations, inventory, events and contacts retain project references. See [DATABASE](../DATABASE.md) for cascade behavior; schema cascade capability is not authorization to delete a project.

## Important business rules

- Completed projects cannot be used for many new/edit workflows without reactivation; inspect the actual operation because enforcement is distributed across UI and database methods.
- Completion's attendance checks are blockers; unpaid/unverified expenses, incomplete tasks and outstanding advances are warnings, not an automatic requirement that every balance be zero.
- Contract cost limit is independent of physical cash/deposits. Borrowing can fund a cost without redefining its owning project.
- A funding project and an expense project may differ. Client-direct purchases still belong to the intended construction project.

## Inputs and outputs

Inputs: project/client/contract/dates/address, heads, phases/tasks, and completion/reactivation authorization/notes. Outputs: project IDs and seeded classifications, scoped views, budget metrics, audit records and completion snapshots. Creating a project does not receive money or post costs.

## Dependencies on other modules

All financial modules use project identity. Employees/attendance use work projects and heads; payroll creates project expenses. Cash operations distinguish allocation/receipt owner from cost owner. Reporting aggregates selected projects.

## Workflow example

Create a project and its contract limit, then record funding and expenses separately. At completion, resolve attendance blockers, review warnings and retain the generated snapshot rather than deleting the project.

## Known limitations or technical debt

No dedicated company-accounting entity exists: Montarra is represented as a project plus classifications. Some historic repair logic finds projects by specific names. Dashboard metrics use several different bases; captions must not hide these differences. Closeout is an operational snapshot, not a general-ledger period lock.

## Important invariants and tests

Preserve IDs and closeout history; reactivate rather than erase completed records. Never substitute contract remaining for cash available. Cross-project transfers must balance at company scope without duplicating costs. Coverage: project lifecycle tests in `test_app.py`, cost/commit limits in `test_project_funding.py`, and reporting tests.
