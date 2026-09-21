# Standard Inno Setup updater (v1.7.5)

Compile installer.iss using an official publisher-signature-verified Inno Setup compiler. The local build used the portable 7.1.0 x64 compiler whose distribution signature validates as Pyrsys B.V. Preserve upstream copyright notices and use its published license: https://jrsoftware.org/files/is/license.txt. Inno Setup is by Jordan Russell and Martijn Laan.

Build inputs: installer.iss, build_release.ps1, tested app.py/app_clean.py, README.md, UPDATE_GUIDE.txt and release_payload containing the tested runtime and existing ConTracktor_v1.exe launcher. The launcher can be reproduced from launcher.cs using the Windows .NET Framework compiler. Runtime/compiler binaries and client databases are not checked into Git.

Run build_release.ps1 -Compiler <path-to-ISCC.exe>. It rejects database files in the payload and produces the EXE plus SHA256SUMS.txt. No obfuscation, encrypted payload, exclusions or antivirus-policy changes are used.

Test only in isolated directories using /DIR, CONTRACTOR_INSTALL_TEST_DIR, CONTRACTOR_INSTALL_TEST_DATA_DIR and CONTRACTOR_DB_PATH. Test mode suppresses user shortcuts and registry writes. Production requires the app/database to be closed and backs up app/data files before replacement.

This is a prerelease packaging-remediation candidate. The original reported Wacatac detection remains pending Microsoft review; local scans are not clearance. See SECURITY_REVIEW_1.7.5.md in the repository.
