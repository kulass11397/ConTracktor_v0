# ConTracktor_v1 1.5.0 — Inventory and operations update

## Project Inventory prototype

- Added a dedicated Inventory tab with an independent project selector.
- Registers consumable materials and non-consumable tools with stable item and transaction references.
- Tracks opening stock, restocks, consumable usage, remaining quantities, reorder levels and low-stock status.
- Links material issuance to active employees and records the purpose of every usage entry.
- Tracks tool borrowing, responsible employee, partial returns, final returns, condition and outstanding custody.
- Prevents issuing more consumable stock or tools than are available.
- Requires an active project-head PIN for every inventory-changing action.
- Locks inventory changes after project completion while retaining its full read-only closeout history.

## Other recent operations updates included

- Completed-project closeout and reactivation controls.
- Employee archive/reactivation and movement between projects.
- Closed-attendance correction with audit history and payroll-adjustment safeguards.
- Multi-select expense filters and the latest expense, payroll, remittance and validation fixes.

## Installer safeguards

- Update-only package: it never bundles or replaces the client's SQLite database.
- Makes timestamped backups of the current database, WAL/SHM sidecars and prior application files.
- Adds new tables through additive database migration on first launch.
- Rejects unsafe embedded paths and refuses to update while the installed app is open.

Verification: 31 automated tests passed; full nine-page Tkinter startup passed; SQLite integrity is OK.
