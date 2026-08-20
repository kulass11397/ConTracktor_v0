# ConTracktor_v1 1.3.0

This is a data-preserving application update. The installer excludes SQLite
database files and creates timestamped application and database backups before
replacing program files.

## Expense-entry workflow

- Added an Excel/Google Sheets-ready batch-expense import form.
- Added live dropdown values exported from the local database.
- Added declared-batch-total reconciliation and all-or-nothing row validation.
- Added an import review screen showing every invalid row before commit.
- Removed the unused Unit field from expense-entry workflows.

## Form validation

- Missing required inputs remain open and flash red.
- Invalid dates and common numeric inputs remain open and flash red.
- Applied the same in-place feedback to employee, project, cash-advance batch,
  recovery, and reusable fill-out dialogs.

## Retained recent features

- Saturday-Friday payroll workweeks and repaired deduction date assignment.
- Batch employee cash advances and payroll deduction reconciliation.
- Employee birthday picker with scrollable year/month/day selection.
- Project-head PIN editing.
- Bank-account transfers, references, cash allocation, surrender, and remittance
  reconciliation improvements from prior updates.
