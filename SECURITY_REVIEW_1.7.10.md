# Security review - ConTrackTor v1.7.10

- Standard Inno Setup updater with no one-file packer, obfuscation, encrypted payload, or self-extraction code.
- No client database or SQLite sidecar is included.
- Installation is blocked while the live database is open, and timestamped application/database safety backups are created before replacement.
- Attendance deletion is limited to uncommitted records and requires a correction reason plus a final confirmation.
- Deleted attendance is removed from live payroll calculations but retained in the audit trail with employee, work site, times, gross amount, reason, and approving head.
- Attendance tied to committed payroll remains protected until the payroll is reopened through the existing reversal workflow.
- No Defender exclusions, firewall rules, services, scheduled tasks, startup persistence, or security-policy changes are installed.
- The release includes a SHA-256 checksum for integrity verification.

This remains an unsigned prerelease. A clean scan applies only to the exact published artifact and cannot guarantee another computer's cloud-reputation decision.
