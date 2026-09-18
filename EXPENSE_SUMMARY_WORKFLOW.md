# Client expense-summary PDF

From Expenses, select the project(s), reporting dates and other ledger filters, then use the existing Export PDF action. Choose Summary Only, Summary + Detailed Ledger, or Detailed Ledger Only.

The report title, address, reporting-period label and comma-separated signature names can be edited for that export. This does not rename a project or modify transactions. Signatures appear only on the last page.

The summary includes selected-period construction costs, gross committed payroll/recorded labor, bank charges, ledger totals, separate employee advance issuances, payments, recoveries, outstanding balances and verification totals. It groups construction costs by phase, category/trade, area and project, and lists recorded payment/allocation sources. The combined report retains all 19 existing detailed-ledger columns.

Running totals include all active expenses in the selected projects through the reporting end date, ignoring other row filters. Funding balances are current at export, not historical bank reconciliation. Materials/other non-labor costs include unclassified procurement; review categories before client approval. Gross labor adds back committed payroll deductions, while cash-advance issuances are excluded from construction costs to avoid charging the same advance twice. Phase/category/area/project tables regroup the same costs and must not be added together. Missing classifications are explicitly Unassigned/Uncategorized. Voided entries and excluded payment history are omitted.

Footer: ContrackTor v1 | Expenses Summary.

Validation: 116 regression tests passed. A UI export smoke test using a disposable copy of the 18 September client backup verified all three choices and unchanged financial/attendance history. Both the revised supplied sample and the system-generated report were rendered and visually inspected. No client database, confidential report or sample records are included in the source update.

This source patch does not replace existing client records and does not publish a new installer. The previous installer version remains unchanged until a new updater is packaged and tested.
