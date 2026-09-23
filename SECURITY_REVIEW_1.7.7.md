# Security review — ConTrackTor v1.7.7

- Standard Inno Setup installer; no one-file packer, obfuscation, encrypted payload, or self-extraction code.
- Application uses a bundled visible Python/Tk runtime and a conventional .NET launcher.
- No client database or SQLite sidecar is included in the payload.
- Installer rejects an open database, creates timestamped application/data backups, and leaves the database byte-for-byte unchanged during installation.
- No Defender exclusions, firewall changes, scheduled tasks, services, startup persistence, command downloaders, or elevation are added.
- The build and release SHA-256 are published for integrity checking.

This remains an unsigned prerelease. A clean local scan is evidence for this exact artifact only and cannot guarantee another machine's cloud-reputation decision.
