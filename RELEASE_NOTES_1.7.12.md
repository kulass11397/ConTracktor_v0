# ConTrackTor v1.7.12 - multi-project expense imports

This update removes the obsolete one-project-per-workbook restriction from the batch-expense import workflow.

- One generated Excel import form can contain expense rows for multiple active projects.
- Every row independently selects its expense project and its funding source.
- Funding sources can be the same project, another project, or **Client Funded (Paid Directly by Client)**.
- The complete workbook is still reviewed as one import and must reconcile to its declared total.
- On commitment, ConTrackTor separates the rows into project-specific expense batches, issues a distinct auditable batch reference for each project, and requests the appropriate project authorization.
- Each committed expense preserves the original import filename, draft reference and spreadsheet row number.
- Existing single-project forms remain compatible. Previously generated forms also work when they contain the existing Project and Funding Source columns.
- Newly generated forms now explain the multi-project workflow directly in the workbook.

Data safety:

- The updater contains no client database.
- Installation does not rewrite existing expenses, funding records, receipts, payroll or cash allocations.
- New financial records are created only when an authorized user reviews and commits an imported expense batch.
- The standard updater blocks installation while the database is open and creates timestamped application and database backups before replacing program files.

Security status: unsigned release. The installer uses standard Inno Setup packaging without obfuscation, encrypted payloads, antivirus exclusions, services, scheduled tasks or startup persistence. Local Microsoft Defender scanning is performed on the exact release artifact, but only code signing and Microsoft reputation can materially reduce false-positive warnings on other computers.
