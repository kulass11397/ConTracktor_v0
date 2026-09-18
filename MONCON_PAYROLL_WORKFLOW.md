# Company-wide employee and payroll views

The main app.py now opens Payroll with an independent, company-wide ledger view.
The project chosen in the app header remains the context for new employees,
deployment, kiosk attendance, cash-advance grants and daily attendance closure.
The Payroll view dropdown is a viewing filter, not a project-transfer action.

## Employee references

- Existing profiles receive unique MONCON-NNN references on first database startup.
- The database is backed up before references are renamed.
- Former references are retained in employee_reference_history and displayed in profiles.
- Roster searches also match former references.
- Kiosk lookup accepts an unambiguous former reference for a currently deployed employee.
- Employee IDs, PINs, assignments, attendance, financial amounts and historical payroll snapshots are preserved.
- New references use a company-wide sequence, including archived profiles.
- Employees remain one profile deployed to multiple sites; names are not automatically merged.

## Unified ledgers

- All active employees are shown by default, without the prior first-20 limit in the roster or weekly summary.
- Weekly Payroll combines staged project wage and deduction shares into one row per employee.
- Archived employees with unpaid staged attendance remain included in the weekly summary.
- Daily attendance and committed payroll ledgers identify the work project.
- Cash Advances identifies the issuing project; CA Outstanding is shown separately from this week's deduction.
- Double-clicking a weekly employee row shows daily logs across the projects in the current view.
- CA PDF export respects the Payroll view filter and the chosen repayment-method filters.
- Payroll commitment still reviews and posts separate expenses per work project, retaining existing authorization.

## Suggested daily workflow

1. Search the company roster and deploy the existing profile to each work site.
2. Record actual attendance segments under their work projects; do not duplicate profiles.
3. Close completed daily attendance per site.
4. Review the company weekly summary, then drill into employee daily logs if needed.
5. Review each site's amounts before committing payroll to expenses.

This update does not invent attendance or change the amount of advances already paid.
Insufficient salary continues to carry unpaid CA balances forward.
The client's supplied backup was used only through temporary copies for testing.

Source backup: Updates/pre_moncon_payroll_20260918_142900.
Client distribution uses the record-preserving v1.7.1 EXE updater and its release-specific deployment instructions.
