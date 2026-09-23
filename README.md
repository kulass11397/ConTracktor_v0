# ConTrackTor — v1.7.6 project-aware cash advance attribution

Local Windows contractor-management system for projects, expenses, petty cash, remittances, company-wide attendance/payroll, advances, inventory and contacts.

The [v1.7.6 prerelease updater](https://github.com/kulass11397/ConTracktor_v0/releases/tag/v1.7.6) separates the project that supplied cash for an advance from the project or projects that ultimately absorb its salary deduction. The Expense ledger attributes CA recoveries to committed payroll work sites, and the Cash Advances ledger displays both **Cash Funder** and **Cost Project(s)**. Batch advance entry now explains this rule before saving.

For the supplied 23 September client backup, the verified Project Grace CA attribution is PHP 5,583.31. Project Oasis remains the original cash funder, preserving the audit trail. Project Grace shows PHP 20,300.00 in gross payroll construction cost: PHP 14,716.69 cash payroll plus PHP 5,583.31 in CA salary deductions.

See [release notes](RELEASE_NOTES_1.7.6.md), [client update guide](UPDATE_GUIDE_1.7.6.txt), and [workflow](MONCON_PAYROLL_WORKFLOW.md).

All earlier feature, development, and deployment documentation is retained in [historical notes](HISTORICAL_FEATURES.md). Use the current guide for installation; older release references there are history, not recommendations.

The standard Inno Setup updater backs up the existing app/database and packages no client records. All 165 regression tests and isolated record-preservation checks pass.

Security notice: local Defender scans are not Microsoft clearance or a guarantee of acceptance on another computer. Do not bypass antivirus protection. See [review status](SECURITY_REVIEW_1.7.6.md).
