# Windows updater build sources (v1.7.1)

The Windows .NET Framework compiler builds the launcher and updater. The updater embeds application source and the previously tested Python/Tk runtime. It contains no database files. App/data backups precede application-file replacement; first startup backs up the database again before MONCON reference migration.

Place app.py, app_clean.py, README.md, UPDATE_GUIDE.txt, these build sources, and release_payload/runtime from the existing Windows distribution together, then run build_release.ps1. Keep CROSS_PROJECT_WORKFLOW.md in release_payload. Runtime binaries and private/client databases are not checked into Git.

Test installation only in isolated folders using CONTRACTOR_INSTALL_TEST_DIR and CONTRACTOR_INSTALL_TEST_DATA_DIR. CONTRACTOR_DB_PATH and CONTRACTOR_SMOKE_TEST=1 permit first-launch verification against a copied database. Never point installer tests at the client's original database.

The publishing script uses Windows Credential Manager authentication without printing or embedding credentials. Installer assets are uploaded separately to the GitHub release; SHA256SUMS.txt verifies the executable.
