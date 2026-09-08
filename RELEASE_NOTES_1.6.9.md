# ConTracktor v1.6.9

This cumulative patch corrects the Petty Cash account limit and centralizes supplier contacts.

## Petty Cash account limit

- Each registered project head may hold up to two active Petty Cash accounts across projects.
- Direct Procurement allocations no longer consume either Petty Cash slot.
- The third active Petty Cash account remains blocked until an earlier PC account is no longer active.
- The rule is based on the project head's shared registry identity, so assigning the same head to another project does not create extra slots.

## Supplier contacts

- Suppliers entered through ordinary expenses, imported batch expenses, expense edits, and Direct Procurement allocations are added to Contacts automatically.
- Existing supplier names are backfilled into Contacts when the updated application first opens.
- Payroll and employee cash-advance payees are excluded because they are not vendors.
- Supplier matching is case-insensitive and reusing a deleted supplier restores it automatically instead of creating a duplicate.
- Deleted suppliers no longer appear in new Direct Procurement suggestions.

## Contacts controls

- Contacts retain Add and Edit controls and now support safe Delete / Restore behavior.
- **Show deleted** displays removed contacts for review and restoration.
- Deleting a contact does not alter or remove historical expenses, payments, or cash allocations.

## Data safety

- This is a code-only cumulative updater; no SQLite database is included.
- The installer preserves the live client database and creates timestamped application and database backups before replacing program files.
- Supplier backfill adds contact-directory rows only and does not change financial amounts, references, payments, or balances.

## Validation

- Python compilation passed.
- All 47 automated tests passed.
- The installer payload is checked to reject any `.db`, `.sqlite`, or `.sqlite3` file.
