# ConTracktor v1.7.6 — project-aware cash advance attribution

This update corrects how cash-advance salary deductions are presented when an employee works on a project other than the project that originally funded the advance.

- The Expense ledger now attributes salary deductions to the employee's committed payroll work project. Payroll cost is shown at gross construction cost, while the original CA expense is reduced by the recovered amount.
- The Cash Advances ledger now separates **Cash Funder** from **Cost Project(s)**. Project filters include CAs funded by that project and CAs recovered through that project's payroll.
- Batch Cash Advances clearly asks for the project supplying the money and explains that final cost attribution follows committed attendance and payroll automatically.
- Cross-project recovery balances remain intact, so the original cash source and the project receiving the labor cost remain auditable.
- Remaining-budget validation for new single and batch advances uses project construction-cost accounting, including inter-project recoverables.

Client-backup verification: the supplied 23 September database resolves exactly PHP 5,583.31 of CA salary deductions to Project Grace. Project Oasis remains the cash funder for those advances. The Grace payroll displays PHP 20,300.00 construction cost (PHP 14,716.69 cash payroll plus PHP 5,583.31 CA deductions), while the Oasis-to-Grace recoverable remains traceable.

Verification: 165 regression checks passed. The standard installer is also tested against an isolated copy of the client database and contains no client records.

Security status: unsigned prerelease. A local Defender scan cannot guarantee acceptance on the client's computer. Do not bypass a warning if one appears; submit the flagged installer for Microsoft review instead.
