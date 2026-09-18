# ConTracktor v1.7.1 — Unified employees and payroll

1. Payroll defaults to all employees across all projects, independently of the project selected for new entries.
2. Employee Roster and Weekly Payroll display all employees instead of only the first 20.
3. Existing employee profiles receive unique company-wide MONCON references; new references follow a company-wide sequence including archived profiles.
4. Former employee references are preserved, displayed in employee profiles, and searchable. Unambiguous former references remain usable at the kiosk for deployed employees.
5. Employee roster search supports names, company/former references, project names and positions.
6. Weekly Payroll consolidates each employee's staged wages, CA deductions and corrections across sites into one row without duplicating project shares.
7. Optional project filtering remains available. Daily attendance and committed payroll ledgers display their work projects.
8. Double-click a weekly employee row to view daily attendance across the sites in the current view and use existing attendance/pay correction controls.
9. CA Outstanding is separate from CA Deduction This Week; missing closed attendance is clearly flagged for employees with outstanding advances.
10. The CA register identifies the issuing project, and its PDF export follows the selected all-projects/project view and repayment-method filters.
11. Payroll commitment still reviews separate project totals, requires existing authorizations, and creates separate project expenses.
12. Installer backs up application/data folders and never contains or replaces a client database. First database startup also backs up records before MONCON reference migration.

Retains all v1.7.0 workflows, including multi-project attendance, proportional CA recovery, cross-project funding, manual WD sourcing and guarded historical WD-link repair.

Verification: 98 regression tests passed. GUI checks on a temporary copy of the 18 September client backup verified all 42 active employees, 51 unique company references, unchanged weekly deductions of PHP 25,077.04, and unchanged attendance/financial records relative to normal existing-release startup.

No sample data or client database is included. Actual missing attendance must still be entered and closed; this update does not invent wages or mark scheduled CA recovery as posted repayment.

The updater is not code-signed. Antivirus and Windows reputation warnings cannot be ruled out; do not disable protection if a detection occurs.
