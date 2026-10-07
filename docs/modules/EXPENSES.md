# Expenses

Implemented reference: active `ExpensesTab`/`BulkExpenseDialog` in `app.py` at `a329efc`; inspected 2026-10-07.

## Purpose

Record cost once under its owning project, distinguish who funds payments, track supplier settlement/verification, and provide source-aware ledger/report views.

## Current implementation

The current expense page integrates Financial Control, Expense Ledger, Cash Operations, Inter-project Funding and receipt/activity views. Bulk entry stages rows before commitment. Excel/CSV import generation and review support multiple expense/funding projects; commitment separates project-specific batches. Persisted drafts do not post costs/payments. Current validation resolves live project, phase, category, bank/allocation and balances; it is not solely a frozen workbook-balance snapshot.

Each expense may have multiple payments/sources. Payment History and Payments/Funding Sources distinguish active source rows from excluded history. Expense verification is separate from supplier payment and project-funding settlement. Clean UI reorganizes controls and financial-detail rows without creating another accounting engine.

## Relevant files/classes/functions

`app.py`: `ExpensesTab`, `BulkExpenseDialog`, `ExpenseImportReviewDialog`, `ExpenseDetailsDialog`, `PaymentHistoryDialog`, `PaymentSourcesDialog`. Helpers: `write_expense_import_form`, `write_expense_import_xlsx`, `read_expense_import_form`, `_read_xlsx_rows`, `expense_ledger_amounts`. `Database`: `record_project_payment`, `reassign_expense_payment`, `_sync_expense_payment_status`, `_sync_project_funding_loan`, `verify_expense_batch`, `set_expense_voided`, draft methods. `ExpensesTab.filtered_rows`, `_expense_funding_context`, `refresh`, `export_pdf` control ledger aggregation.

## Database tables and relationships

`expenses` owns project, phase, item/quantity/unit-price/total, date, category/area/trade, payment/verification/workflow labels and funding/default allocation hints. `payments` supplies actual amount/source/date with bank/allocation/funding project and exclusion flag. `expense_batches` groups committed rows; `workflow_drafts` stores JSON staging. Verification headers/items/approvals preserve signoff. Payroll/CA expenses link to their originating workflows; funding loans link payments to other project views.

## Important business rules

- Expense project owns cost; funding project owns a specific payment's funds. Different funder creates linked inter-project debt, not another expense.
- Client Funded means supplier paid directly by client: cost remains, but company cash/bank/allocation is not consumed. It does not record cash received from client.
- Import rows validate against project-specific phases (including Personal), global categories, source references and current remaining balances; quantity must be positive, price nonnegative, partial payment between zero and total.
- Personal classification does not automatically change the project or supply funds.
- Voiding/restoring an ordinary expense refreshes allocation usage/status and checks restoration capacity. Existing inter-project repayments must be undone before reversal. Committed payroll is corrected through Reopen, not the ordinary expense-void shortcut.

## Inputs and outputs

Inputs: project/funder/client-funded selection, line item dimensions/quantity/unit/price, category/phase, date, supplier/reference, payment state/method/source and authorization. Outputs: staged/draft data, expense batches/rows, payments/allocation transactions/loans, verification/audit history, filtered derived views and exports.

## Dependencies on other modules

Projects supply ownership, cost limits and heads. Cash/bank modules validate payment custody. Payroll/CAs generate linked expenses. Funding module supplies settlement context; reporting interprets recoveries and gross attribution.

## Workflow example

For a Project B purchase paid using Project A funds, enter B as Expense project and A as Funding project, then choose the actual source. For a purchase paid directly by the client, choose Client Funded instead; do not create a company cash disbursement.

## Known limitations or technical debt

Some UI posting/edit paths use direct SQL, and legacy expense code remains. Funding/status classification uses strings. Existing workbooks may not offer recently added reference values even if import can resolve them; refresh references before filling a new form. Imports revalidate funds at commitment but are not a general concurrent multi-user reservation system. Supplier text syncs into contacts through triggers; receipts/documents are not automatically financial entries.

## Important invariants and tests

One underlying expense despite multiple lender/borrower views; payments never exceed total; no client-direct company cash spend; no draft posting; no duplicate gross/CA costs; transaction-safe commitment and guarded reversal. Tests: import/payment/verification cases in `test_app.py`, `test_project_funding.py`, `test_expense_summary.py`, `test_allocation_reactivation.py`.
