# Windows updater build sources (v1.7.0)

The installer and launcher use the Windows .NET Framework C# compiler. The installer embeds a ZIP containing application source and the existing tested Python/Tk runtime. It rejects database files from the payload, backs up existing application/data folders, preserves the active database and replaces application files only.

To reproduce the local build, place these sources in a build directory containing app.py, app_clean.py, README.md, UPDATE_GUIDE.txt and release_payload/runtime from the existing Windows distribution. Add CROSS_PROJECT_WORKFLOW.md to release_payload, then run build_release.ps1. The runtime is not checked into Git. Tests and client databases are not packaged.

Source modules in this repository match the EXE payload. The published release includes the updater and its SHA-256 checksum. Authentication is retrieved from Windows Credential Manager by the optional publishing script and is never printed or embedded in the installer.

Test mode uses CONTRACTOR_INSTALL_TEST_DIR and CONTRACTOR_INSTALL_TEST_DATA_DIR to direct installation to disposable folders without changing normal shortcuts or starting the app automatically. CONTRACTOR_DB_PATH and CONTRACTOR_SMOKE_TEST=1 can then verify first launch on a copied database. Never use the client's original database for this test.
