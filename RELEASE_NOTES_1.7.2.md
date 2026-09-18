# ConTracktor v1.7.2 — standard installer test release

**Security status: candidate replacement, not Microsoft clearance.** The prior v1.7.1 custom updater has a client-reported `Trojan:Win32/Wacatac.B!ml` detection. Keep the flagged download removed. This release is a prerelease pending Microsoft analysis and confirmation on the affected client PC. Do not bypass Defender to test it.

Changes:

1. Replaces the custom .NET embedded-ZIP updater with a standard Inno Setup wizard, built using a publisher-signature-verified official compiler.
2. Keeps the same per-user application and data locations, without shipping a database or sample records.
3. Makes timestamped application/database backups before copying application files.
4. Adds an exclusive database-access check; installation stops if the active database is in use or cannot be safely backed up.
5. Does not launch the app automatically after installation. Open it manually after checking security status.
6. Does not change antivirus settings, install exclusions, modify download protection, restore quarantined files, or conceal components.
7. Preserves the complete tested v1.7.1 application source and all unified employee/payroll features. No financial-calculation changes.

Verification:

- Isolated installation preserved the database byte-for-byte, made application/database backups, and launched with the bundled runtime.
- First-launch comparison preserved attendance and financial fields across nine tables, with 51 unique MONCON profiles and the migration backup present. Existing normal-startup expense-batch metadata grouping remains unchanged in behavior.
- A deliberately open disposable SQLite database blocked installation without changing app/database files.
- Local Windows Defender scanned both the new installer and the unpacked payload and reported no threats (18 September 2026).
- Application source is byte-identical to the v1.7.1 version that passed 98 regression tests.

These local results do not establish that the prior detection was incorrect or guarantee acceptance by another machine's antivirus/cloud reputation checks. No Microsoft review has been completed. The ConTracktor installer/launcher/runtime are not signed with a trusted ConTracktor publisher identity.

Before testing: make a fresh client database backup, close the app, use the same Windows user, and stop if Defender reports a threat. See UPDATE_GUIDE_1.7.2.txt and SECURITY_REVIEW_1.7.2.md in the repository.
