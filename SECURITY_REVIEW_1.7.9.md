# Security review — ConTrackTor v1.7.9

- Standard Inno Setup installer; no one-file packer, obfuscation, encrypted payload, or self-extraction code.
- Application uses a bundled visible Python/Tk runtime and a conventional .NET launcher.
- No client database or SQLite sidecar is included in the payload.
- Installer rejects an open database, creates timestamped application/data backups, and leaves the database byte-for-byte unchanged during installation.
- No Defender exclusions, firewall changes, scheduled tasks, services, startup persistence, command downloaders, or elevation are added.
- Attendance deletion is limited to uncommitted records and retains an audit-log entry. Committed payroll must be reopened before a work-site move or deletion.
- Client-summary and billing exports are read-only. They query selected ledger rows, payroll snapshots, uncommitted completed attendance, and linked project-funding balances without posting transactions.
- Uncommitted payroll is identified by its missing payroll-batch link; committed attendance is excluded from the staged section so it cannot be reported twice.
- The one-time Grace duplicate correction requires exact reference/date/type/amount matches, checks for dependent repayments, creates a database backup, and voids rather than deletes the incorrect bank-deposit record.
- The build and release SHA-256 are published for integrity checking.

This remains an unsigned prerelease. A clean local scan is evidence for this exact artifact only and cannot guarantee another machine's cloud-reputation decision.
