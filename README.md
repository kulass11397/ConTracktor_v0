# ConTrackTor — v1.7.7 visible payroll CA audit trail

Local Windows contractor-management system for projects, expenses, petty cash, remittances, company-wide attendance/payroll, advances, inventory and contacts.

The [v1.7.7 prerelease updater](https://github.com/kulass11397/ConTracktor_v0/releases/tag/v1.7.7) adds individual blue CA deduction audit lines to each payroll project's Expense Ledger. Every line retains its employee, original cash funder, cost project, payroll batch and recovery trail without being counted as a second expense.

For the supplied 23 September client backup, the verified Project Grace CA attribution is PHP 5,583.31. Project Oasis remains the original cash funder, preserving the audit trail. Project Grace shows PHP 20,300.00 in gross payroll construction cost: PHP 14,716.69 cash payroll plus PHP 5,583.31 in CA salary deductions.

See [release notes](RELEASE_NOTES_1.7.7.md), [client update guide](UPDATE_GUIDE_1.7.7.txt), and [workflow](MONCON_PAYROLL_WORKFLOW.md).

All earlier feature, development, and deployment documentation is retained in [historical notes](HISTORICAL_FEATURES.md). Use the current guide for installation; older release references there are history, not recommendations.

The standard Inno Setup updater backs up the existing app/database and packages no client records. All 167 regression tests and isolated record-preservation checks pass.

Security notice: local Defender scans are not Microsoft clearance or a guarantee of acceptance on another computer. Do not bypass antivirus protection. See [review status](SECURITY_REVIEW_1.7.7.md).
