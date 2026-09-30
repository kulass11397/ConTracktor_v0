# ConTrackTor — v1.7.11 project cash accounts

Local Windows contractor-management system for projects, expenses, petty cash, remittances, company-wide attendance/payroll, advances, inventory and contacts.

The [v1.7.11 updater](https://github.com/kulass11397/ConTracktor_v0/releases/tag/v1.7.11) adds a visible cash-account owner selector, separates receipt-owned reimbursement and retained cash, and supports expenses paid directly by clients without consuming Montarra funds.

See [release notes](RELEASE_NOTES_1.7.11.md), [client update guide](UPDATE_GUIDE_1.7.11.txt), and [security review](SECURITY_REVIEW_1.7.11.md).

All earlier feature, development, and deployment documentation is retained in [historical notes](HISTORICAL_FEATURES.md). Use the current guide for installation; older release references there are history, not recommendations.

The standard Inno Setup updater backs up the existing app/database and packages no client records. Financial, payroll, attendance, expense, cash-allocation and installation regression tests are run before publishing.

Security notice: local Defender scans are not Microsoft clearance or a guarantee of acceptance on another computer. Do not bypass antivirus protection. See [review status](SECURITY_REVIEW_1.7.11.md).
