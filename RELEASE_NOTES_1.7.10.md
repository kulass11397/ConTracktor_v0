# ConTrackTor v1.7.10 - attendance-log deletion correction

This record-preserving patch broadens the weekly payroll attendance correction workflow.

- Replaces **Delete Duplicate Log** with **Delete Selected Log** in the employee's weekly attendance detail window.
- Allows any incorrect uncommitted attendance log in the selected week to be deleted, including an accidental open clock-in.
- Requests a required correction reason before deletion.
- Shows a final Confirm/Cancel window identifying the employee, work site, time range, gross amount removed, and reason.
- Recalculates the employee's daily regular/overtime split, daily-close totals, weekly payroll totals, and weekly attendance grid after deletion.
- Preserves a permanent `ATTENDANCE_LOG_DELETED` audit entry containing the deleted log's details, reason, and approving project head.
- Continues to block deletion when the attendance is tied to a committed payroll. The payroll must be reopened first so its expense, payments, deductions, and project splits are reversed safely.
- The updater contains application files only and preserves the client's current database.

Verification: all 173 automated tests pass, including ordinary completed-log deletion, accidental open-clock-in deletion, committed-payroll safeguards, weekly-grid recalculation, payroll, expenses, cash advances, and inter-project funding tests.

Security status: unsigned prerelease. The exact installer is scanned with Microsoft Defender before publishing, but code signing and Microsoft reputation are still required to materially reduce false-positive warnings on other computers.
