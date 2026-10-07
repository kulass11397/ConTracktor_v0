# Attendance

Implemented reference: current `app.py`/`app_clean.py` working tree based on `a329efc`; inspected 2026-10-07.

## Purpose

Record actual employee work times/sites and produce correct, auditable input to weekly payroll.

## Current implementation

The active Batch attendance action opens `WeeklyAttendanceGridDialog`. The legacy `BatchAttendanceDialog` remains in source but is not the current normal batch entry point. Kiosk clock-in/out is also implemented.

The weekly grid loads recorded work plus separate draft cells for Saturday–Friday. A blank cell contributes no draft day/pay; Absent is a mark, not worked time; Present requires segments. Preview combines existing uncommitted completed attendance with draft segments, estimates gross/CA deductions/adjustments and does not post deductions. Finalization authorizes affected projects, validates overlaps/locks, writes work or absence marks and closes the appropriate days. Saving a draft alone creates no attendance/payments.

Each project tab initially shows active employees whose deployment overlaps any part of the selected Saturday–Friday week. Employees with existing attendance, absence marks or saved draft cells for that project/week remain visible. An operator may show any other active company employee through the tab's Additional employee dropdown; this changes only the batch-grid roster and does not create or modify a deployment. The All Projects review tab shows the union of employees visible in the project tabs.

The weekly grid can generate one Excel workbook for the selected week. It creates one visible tab per active project, preloads that tab's current grid roster, and provides blank employee-dropdown rows for other active company employees. Each day uses one cell: `P` means 08:00–17:00 present, `A` means absent, and `HH:MM-HH:MM` segments support half days, undertime and split shifts. Existing recorded/finalized attendance is displayed as a read-only marker.

The workbook may be uploaded to Google Sheets for shared editing and downloaded again as `.xlsx`. Import identifies each project from fixed metadata inside its sheet, not from the tab name, hidden reference sheet, formatting, validation rules, formulas or ZIP/XML ordering. Renaming a project tab or losing workbook formatting therefore does not invalidate an otherwise intact file. Import is all-or-nothing: it rejects a changed week/project/version/header, missing or duplicate project sheet, unknown/duplicate employee, changed read-only marker, invalid time or cross-site overlap. A successful import only replaces the unsaved on-screen grid; the existing Save Weekly Draft and project-head finalization steps remain required.

## Relevant files/classes/functions

`app.py`: `WeeklyAttendanceGridDialog`, `KioskWindow`, `AttendanceEditDialog`, `WeeklyEmployeeDetailsDialog`, active `PayrollTab`. `Database`: `employees_deployed_during`, `_validated_weekly_cells`, `save_weekly_attendance_draft`, `preview_weekly_attendance_payroll`, `finalize_weekly_attendance_draft`, `record_batch_project_attendance`, `_recalculate_employee_day_segments`, `close_attendance_day`, `revise_attendance`, `delete_attendance_log`. Helpers: `compute_shift_pay`, `payroll_week_bounds`, `write_weekly_attendance_xlsx`, `read_weekly_attendance_xlsx`, `_read_xlsx_worksheets`.

## Database tables and relationships

`attendance` references employee and records work project, shift/pay/rate, closure and payroll links. `weekly_attendance_drafts` stores Present/Absent cells with JSON segments; `weekly_attendance_marks` stores finalized absence. `attendance_closure_batches` aggregates closed project-days. `attendance_revisions` retains correction values and authorization. Payroll snapshots preserve committed details; `payroll_adjustments` carries relevant corrections forward.

## Important business rules

- Reject overlapping segments for one employee across any projects. Touching segments are allowed. Manual batch segments finish later on the same date.
- Lunch overlap with 12:00–13:00 is unpaid. Regular hours are limited across the whole employee-day, not restarted at each site.
- Rate lookup uses actual work project/date. Manual batches require active employee/project, not prior deployment. Deployment controls the initial project-tab roster only; the dropdown may add any active employee without changing deployment history.
- Workbook employee matching uses the active employee's MONCON number. An employee selected in a blank workbook row may be added to that project's grid without creating a deployment.
- Workbook import never saves or finalizes attendance automatically. It validates the complete workbook first, then stages one replacement grid in memory.
- Only completed attendance is correctable through `revise_attendance`. Work-site/week moves and locked multi-project corrections require reopening affected payrolls.
- Deletion permits open or completed uncommitted logs, not only duplicates. It requires a reason and valid project head and is blocked by commitment/week locks. Deletion recalculates remaining day segments and closure totals and writes an audit summary.

## Inputs and outputs

Inputs: employee, project, dates, clock times, day type/rate/pay overrides where supported, grid state, generated/returned weekly `.xlsx`, reason and authorizing head. Outputs: project-tab workbook, staged/imported grid cells, draft cells, attendance/absence/closure records, preview figures, revisions/adjustments and audit entries. Changes refresh payroll/grid views; they do not automatically disburse pay.

## Dependencies on other modules

Employees supply identity and effective rates; projects supply sites/heads. Payroll consumes closed work and locks shared weeks. CAs supply preview deductions; reports may include uncommitted completed/closed labor according to the relevant summary path.

## Workflow example

Mark a split day Present at two sites with nonoverlapping segments. Preview the shared daily gross and pending CA deduction, save/finalize the grid, then commit payroll separately. Leave a cell blank when no draft work should be added.

## Known limitations or technical debt

UI and persistence paths are numerous. Draft cells are not the same as attendance rows, and blank is not identical to an explicit absence. Timestamps are text. The shared-sheet workflow is file based; ConTracktor does not directly synchronize a live Google Sheet, and import requires an `.xlsx` export with the fixed per-project metadata and headers intact. Deleting attendance is physical deletion with audit retention; this is not universal soft deletion. Day-type calculations are limited implemented multipliers, not comprehensive payroll-law handling.

## Important invariants and tests

No pay for blank/absent cells; no overlap/double-paid employee time; one shared daily regular limit; no silent mutation of a frozen multi-project week; preserved committed snapshots. Tests: `test_weekly_grid.py`, `test_company_batches.py`, relevant correction/deletion tests in `test_app.py` and `test_project_funding.py`.
