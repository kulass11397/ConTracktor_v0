# ConTracktor — v1.7.3 batch-workflow update

Local Windows contractor-management system for projects, expenses, petty cash, remittances, company-wide attendance/payroll, advances, inventory and contacts.

The [v1.7.3 prerelease updater](https://github.com/kulass11397/ConTracktor_v0/releases/tag/v1.7.3) removes the top-project prerequisite for batch attendance and batch cash advances. Employees belong to MONCON and can work non-overlapping segments at multiple sites in one day. Advances use an explicit funding project inside the batch window; salary deductions remain employee-wide and proportional to actual work-site earnings.

See [release notes](RELEASE_NOTES_1.7.3.md), [client update guide](UPDATE_GUIDE_1.7.3.txt), and [workflow](MONCON_PAYROLL_WORKFLOW.md).

All earlier feature, development, and deployment documentation is retained in [historical notes](HISTORICAL_FEATURES.md). Use the current guide for installation; older release references there are history, not recommendations.

The standard Inno Setup updater backs up the existing app/database and packages no client records. 107 regression tests and isolated record-preservation checks passed.

Security notice: local Defender scans are clean, but Microsoft review and client download acceptance remain unconfirmed following the earlier v1.7.1 Wacatac report. Do not bypass antivirus protection. See [review status](SECURITY_REVIEW_1.7.3.md).
