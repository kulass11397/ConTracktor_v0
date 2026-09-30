# ConTrackTor v1.7.11 - project cash accounts and client-funded expenses

This financial-control update makes project-owned receipt cash visible without duplicating or rewriting client transactions.

- Adds **Cash account owner** to Allocate Available Cash.
- When the application is on **All Projects**, the dialog now opens in **All Project Cash Accounts** instead of silently defaulting to the first alphabetical project.
- Displays receipt-owned cash accounts separately with their project owner and RCA reference.
- For the reviewed Grace receipt, the existing trail is shown as **PHP 125,804.00 Oasis inter-project reimbursement cash** and **PHP 9,896.00 Grace retained receipt cash**.
- Infers the correct allocation owner when one project receipt account is selected.
- Prevents one PC/DP allocation from mixing receipt cash owned by different projects.
- Adds **Client Funded (Paid Directly by Client)** to the batch-expense funding choices.
- Client-funded expenses remain in the expense project's ledger without consuming Montarra cash, a bank balance, PC/DP cash, or creating an inter-project borrowing.
- Updates the dashboard to distinguish client funds received, total accounted project cost, reimbursed receipt cash, retained receipt cash and outstanding amounts owed to funding projects.

Data safety:

- The updater contains no client database.
- Receipt cash accounts are derived from existing receipt and repayment records; the installer does not rewrite the PHP 135,700 receipt or unrelated client records.
- A table-by-table verification against the reviewed staging database confirmed that all 51 tables and every row remained unchanged after opening the update.
- Actual data changes occur only when an authorized user performs a new operation, such as creating a PC/DP allocation.

Security status: unsigned release. The installer uses standard Inno Setup packaging without obfuscation, encrypted payloads, antivirus exclusions, services, scheduled tasks or startup persistence. Local Microsoft Defender scanning is performed on the exact release artifact, but only code signing and Microsoft reputation can materially reduce false-positive warnings on other computers.
