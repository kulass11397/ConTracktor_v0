# Security review - ConTrackTor v1.7.11

- Standard Inno Setup updater with no one-file packer, obfuscation, encrypted payload or self-extraction code.
- No client database, SQLite journal, WAL or SHM file is packaged.
- Installation is blocked while the live database is open.
- Timestamped application and database safety backups are created before application files are replaced.
- The reviewed database was compared table by table before and after application initialization: all 51 tables and every row were unchanged.
- The PHP 135,700 Grace receipt is not duplicated or rewritten. Its PHP 125,804 Oasis reimbursement account and PHP 9,896 Grace retained account are derived from the existing receipt/repayment audit trail.
- Client-funded batch expenses do not consume project cash, bank cash, PC/DP allocations or create inter-project debt.
- No Defender exclusions, firewall rules, services, scheduled tasks, startup persistence or security-policy changes are installed.
- The release includes a SHA-256 checksum for integrity verification.

This is an unsigned release. A clean local scan applies only to the exact published artifact and cannot guarantee another computer's Microsoft cloud-reputation decision. Code signing remains the durable mitigation for reputation-based warnings.
