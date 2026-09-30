# Security review - ConTrackTor v1.7.12

- Standard Inno Setup updater with no one-file packer, obfuscation, encrypted payload or self-extraction code.
- No client database, SQLite journal, WAL or SHM file is packaged.
- Installation is blocked while the live database is open.
- Timestamped application and database safety backups are created before application files are replaced.
- The feature change affects import validation and generated form instructions; it does not run a data migration or rewrite existing financial records.
- Multi-project imports create records only after complete review, declared-total reconciliation and project authorization.
- The isolated installation test preserved the reviewed database byte-for-byte through installation and first launch, created both application and database backups, and installed source identical to the tested payload.
- The locked-database test correctly refused installation without changing either the application or database.
- Microsoft Defender scanned the exact release EXE on 30 September 2026 and reported no threats.
- No Defender exclusions, firewall rules, services, scheduled tasks, startup persistence or security-policy changes are installed.
- The release includes a SHA-256 checksum for integrity verification.

This is an unsigned release. A clean local scan applies only to the exact published artifact and cannot guarantee another computer's Microsoft cloud-reputation decision. Code signing remains the durable mitigation for reputation-based warnings.
