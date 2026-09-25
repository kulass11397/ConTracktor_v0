# ConTrackTor v1.7.8 — Project Grace reconciliation and traceable repayments

This record-preserving update completes the reviewed Project Grace week-one correction and makes internal project repayments operationally traceable.

- Records the confirmed PHP 135,700 Project Grace payment dated 2026-07-21 as **Cash Received on Hand**, not as a bank deposit.
- Corrects A2R-50233-01 from PHP 10,625 to PHP 10,265 through its linked expense, payment, funding, and allocation audit layers.
- Preserves the existing PHP 1,639 hardware entry, existing professional-service entries, and committed payroll rather than duplicating them.
- Adds only the reviewed missing balances and six client-paid material records. Client-paid purchases increase Grace project cost without consuming Montarra cash.
- Produces PHP 125,804 in reviewed Oasis-to-Grace funding principal. The PHP 9,896 balance consists of the PHP 9,819 management fee and PHP 77 client credit.
- Inter-project repayments now require a traceable source: a physical cash receipt, unallocated cash on hand, or an enrolled bank account.
- The Inter-project Funding ledger supports multi-selection and batch repayment. Individual entries retain their own IPR references and share an IPRB batch reference.
- Cash repayments move project ownership from Grace to Oasis while leaving total company cash unchanged. Undo restores the original source and retains the audit trail.
- The weekly attendance grid now shows projected gross payroll, eligible CA deductions, corrections, and net payable before saving.
- The batch cash-advance window keeps **Stage Selected Employees**, draft, edit, remove, review, and cancel actions visible in the normal layout.
- Project-filtered cash calculations follow the payment's actual funding project rather than incorrectly charging the expense project.

Verification: 91 automated regression checks passed. The reviewed client database was also migrated and batch-settled in an isolated copy: PHP 135,700 receipt, PHP 125,804 repayment principal, and PHP 9,896 remaining. No client database is included in the installer.

Security status: unsigned prerelease. A local Microsoft Defender scan is performed before publishing, but only code signing and Microsoft reputation can materially reduce future false positives. Never disable Defender or add an exclusion to install the update.
