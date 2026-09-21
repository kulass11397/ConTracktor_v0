# ConTracktor v1.7.4 — weekly attendance and expense reporting

New in this release:

1. Weekly attendance opens from Payroll without first selecting a project. A single Saturday–Friday window has one tab per active project and an All Projects review tab; all tabs use the same company employee roster.
2. Click an empty project/day cell for the default 08:00–17:00 present shift. Click a marked cell or right-click to edit one or more time segments. Double-click marks absent. Two sites on the same day are allowed when work times do not overlap.
3. Save Weekly Draft retains the grid without changing payroll. Review and Finalize Week records approved shifts, retains finalized absence marks, and closes affected project days for the existing weekly payroll flow. Existing posted attendance is read-only in the grid and can still be edited through the established correction workflow.
4. Expense PDF export now asks for project scope, date span, report title/address, period label and billing details. Reports include weekly construction-cost breakdowns, running totals, financial/payment summaries, and phase/category/area/project views.
5. The optional billing layout adds separate construction expenses and management fee pages with separate signatures, plus committed payroll employee breakdown pages when the selected ledger includes payroll expenses. The management fee defaults to 15% and is a report calculation, not a ledger posting.
6. The installer updates app files only, performs timestamped app/data backups, and does not bundle or replace the client's database.

Verification: 121 application regression tests passed, including draft/finalized attendance, split-site overlap checks, billing arithmetic and GUI tab creation. The PDF was rendered and visually checked. Isolated installer and Defender results should be reviewed in the release verification record before client deployment.

Security status: unsigned prerelease candidate. A local clean scan cannot guarantee that Microsoft Defender or SmartScreen will allow download on another computer. Do not bypass detections; submit a false-positive sample to Microsoft if flagged.
