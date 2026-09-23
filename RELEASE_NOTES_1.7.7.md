# ConTrackTor v1.7.7 — visible Project Grace CA audit trail

This update makes every posted cash-advance salary deduction visible in the correct payroll project's Expense Ledger without creating duplicate expenses.

- The Expense Ledger now shows blue **CA detail** rows for each employee deduction attributed to the selected payroll project.
- Each detail row identifies the employee, CA reference, deduction amount, original cash-funding project, payroll cost project, payroll batch, allocation/withdrawal trail, and inter-project recovery balance.
- Double-clicking a CA detail row explains that it is already included in the payroll's gross construction cost and is excluded from ledger totals.
- CA detail rows are read-only audit links. Editing, payment, verification, and void actions remain on the original CA/payroll records, preventing accidental duplicate postings.
- New payrolls and deductions are discovered dynamically from the live database. The installer does not rely on a fixed list from the supplied backup.

Client-backup verification: Project Grace payroll batch `PAYW-20260912-0006` contains PHP 5,583.31 in 14 posted deduction transactions. The payroll cost is correctly PHP 20,300.00: PHP 14,716.69 cash payroll plus PHP 5,583.31 in CA deductions. Project Oasis remains the original cash funder, with the Oasis-to-Grace recovery trail preserved.

Verification: 167 regression checks passed. The update was also validated against an isolated copy of the supplied 23 September client database. No client records are packaged in this installer.

Security status: unsigned prerelease. A local Microsoft Defender scan is performed before publishing, but only code signing and Microsoft reputation can materially reduce future false positives. Never disable Defender or add an exclusion to install the update.
