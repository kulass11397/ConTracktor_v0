# Reporting and billing

Implemented reference: `app.py`/`app_clean.py` at `a329efc`; inspected 2026-10-07. Read [ACCOUNTING_RULES](../ACCOUNTING_RULES.md).

## Purpose

Explain construction costs, funding, custody and outstanding obligations without confusing receipts, expenditures and internal transfers.

## Current implementation

Dashboard, Expense Ledger and Financial Control recalculate figures from operational records. Ledger filters include projects, payment/verification/method, area/supplier/search, funding source, Funded by, settlement and dates. Derived lender-recoverable/CA attribution rows can represent linked views rather than independent expenses.

Built-in expense PDF modes include summary, detail and combined views with editable export metadata/signatories. Reports separate CA issuance from construction costs, show gross labor, regroup costs by phase/category/area/project and list payment sources. Running totals honor selected projects/end cutoff but ignore other row filters. Funding balances are current at export, not a historical bank reconciliation.

Optional billing adds a configurable fee to reimbursement. Default reimbursement selects outstanding ordinary Expense funding loans in the selected expense set; manual amount and None are supported. CA-recovery loans are not automatically included in that default ordinary-loan selection. Billing does not post accounting records. Payroll and CA have their own PDFs. Bespoke Grace week reports created outside the app are not permanent built-in templates or authoritative live records.

## Relevant files/classes/functions

`app.py`: `expense_ledger_amounts`, `build_uncommitted_payroll_context`, `build_expense_client_summary`, `build_expense_billing_context`, `write_expense_ledger_pdf`, payroll/CA PDF helpers, `ContractorApp.export_text`. `Database`: `dashboard_financial_summary`, `financial_control_position`, `financial_control_receipts`, `financial_control_projects`, budget and recovery methods. `ExpensesTab.filtered_rows/refresh/export_pdf`; `ProjectsTab.refresh`. `app_clean.py` metric/detail toggles and page layout.

## Database tables and relationships

Reports derive from projects, expenses/payments, payroll batches/snapshots, attendance, advances/recoveries, funding loans/repayments, remittances, allocations/returns/redeposits and receipt placements. `app_metadata` may classify reviewed receipt reimbursement, fee and client credit. No general report-generated receivable/invoice/management-fee journal table is created by billing.

## Important business rules

- Receipt total need not equal construction cost. Supplier outstanding need not equal debt to funding projects.
- Add back applicable payroll deductions for gross construction labor and avoid counting advance issuance again.
- Repeated derived views of one expense must not duplicate totals. Phase/category/area/project grouping totals are alternatives, not additive categories.
- Report staged payroll can include eligible uncommitted attendance without another committed payroll row; it must be clearly labelled and not duplicated after commit.
- Fee basis is the report's construction total. Tools/equipment or Personal classification is not a universal automatic 15% exemption. Select/classify/exclude intended costs deliberately; do not infer the client's old agreement as implemented behavior.
- Retained receipt balance is not automatically fee revenue. Metadata labels can describe historical classifications, while live ownership/repayment figures derive from current links.

## Inputs and outputs

Inputs: project/date/ledger selections, report mode/title/address/signatories, billing percentage and reimbursement mode/manual amount. Outputs: read-only financial summaries, source/grouping tables and PDF/text files. XLSX expense forms belong to the expense import workflow, not posted report balances.

## Dependencies on other modules

All financial modules supply reporting data. Employee/attendance and payroll snapshots supply labor detail. Cash operations and bank transactions supply holdings; funding supplies separate settlement totals.

## Workflow example

Select a project and reporting period, review construction cost and separate supplier/funder outstanding, then generate summary plus billing with the intended fee basis. The PDF shows an amount due but posts no receivable or payment.

## Known limitations or technical debt

Raw database totals, ledger-attributed totals, cost budget and construction summary do not share one universal formula. Current funding metrics combined with period costs do not create an as-of historical balance sheet. Custom PDF rendering uses its own text/width/pagination logic. There is no automatic revenue recognition, editable Word report generator or hardcoded all-project bespoke financial PDF workflow demonstrated by the current core.

## Important invariants and tests

Exports must not mutate financial records; no duplicate costs/recovery; consistent regrouping; retained exact cents; filters and running totals must be labelled honestly; fee generation posts nothing. Coverage: `test_expense_summary.py`, `test_weekly_grid.py`, snapshot/PDF tests in `test_app.py` and company-wide CA export tests in `test_company_payroll.py`.

## Historical-note conflicts

Older workflow files contain dated test counts and old UI paths. Preserve them as history, not current verification promises. In particular, old deployment prerequisites do not describe current manual batch attendance. Standalone reports discussed in earlier threads may contain confirmed manual corrections not replayed by a fresh code checkout; do not replace live data with their totals.
