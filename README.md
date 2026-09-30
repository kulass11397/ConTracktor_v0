# ConTrackTor — v1.7.12 multi-project expense imports

Local Windows contractor-management system for projects, expenses, petty cash, remittances, company-wide attendance/payroll, advances, inventory and contacts.

The [v1.7.12 updater](https://github.com/kulass11397/ConTracktor_v0/releases/tag/v1.7.12) allows one generated expense-import workbook to contain rows for multiple expense projects and funding projects. On commitment, rows are separated into auditable project-specific batches.

See [release notes](RELEASE_NOTES_1.7.12.md), [client update guide](UPDATE_GUIDE_1.7.12.txt), and [security review](SECURITY_REVIEW_1.7.12.md).

All earlier feature, development, and deployment documentation is retained in [historical notes](HISTORICAL_FEATURES.md). Use the current guide for installation; older release references there are history, not recommendations.

The standard Inno Setup updater backs up the existing app/database and packages no client records. Financial, payroll, attendance, expense, cash-allocation and installation regression tests are run before publishing.

Security notice: local Defender scans are not Microsoft clearance or a guarantee of acceptance on another computer. Do not bypass antivirus protection. See [review status](SECURITY_REVIEW_1.7.12.md).
