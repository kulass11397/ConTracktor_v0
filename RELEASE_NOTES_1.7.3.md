# ConTracktor v1.7.3 — company-wide batch attendance and advances

Security status: prerelease candidate. Microsoft review and affected-client acceptance remain unconfirmed. Do not bypass a Defender detection.

Updates:
1. Batch attendance opens without requiring the top project selector.
2. All active MONCON employees can be selected, regardless of home project or prior deployment.
3. Each attendance segment records its actual active work project. Existing project-specific rates apply when valid on that work date; otherwise the employee's standard rate applies.
4. Two or more work sites per employee per day are supported when their time segments do not overlap. Adjacent segments are allowed; overlapping staged or existing logs are rejected.
5. Daily regular/overtime hours remain shared across sites, not reset per project. Lunch 12:00–13:00 remains unpaid.
6. Batch cash advances open from the entire active MONCON roster without requiring the top project selector.
7. A Funding project field inside the advance window identifies the project whose budget and expense ledger fund the advance. It does not filter employee eligibility or select their work site.
8. Scheduled salary deductions retain the employee-wide weekly cap and automatic proportional distribution across actual work-project earnings. Deductions are never duplicated per project.
9. Advance drafts are accessible company-wide, save their funding project, and preserve staged entries when authorization is cancelled.
10. Updates the payroll view hint to explain the company-wide workflow.
11. Retains standard Inno Setup packaging, database-in-use protection and timestamped app/data backups; no client database is included.

Verification:
- 107 application regression tests passed, including mobile employees, split days, overlap prevention, proportional deductions, all-project batch entry, explicit funding accounting, drafts and cancellation.
- Isolated client-backup GUI and installer checks retained existing attendance and financial history.
- Local Windows Defender scans of the installer and unpacked payload reported no threats on 18 September 2026.

Local scans do not establish Microsoft cloud/download approval. The updater remains unsigned, and the previously reported Wacatac detection has not been adjudicated by Microsoft. This release remains a prerelease pending security review/client confirmation.
