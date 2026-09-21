import unittest
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path

from app import PayrollTab
from app_clean import CleanContractorApp
from test_project_funding import ProjectFundingTests


class CleanWeeklyMenuTests(unittest.TestCase):
    def test_clean_attendance_menu_opens_weekly_grid_first(self):
        self.assertTrue(callable(PayrollTab.open_weekly_attendance_grid))
        page=SimpleNamespace(
            add_employee=Mock(),deploy_existing_employee=Mock(),
            open_employee_profile=Mock(),edit_employee=Mock(),archive_employee=Mock(),
            open_weekly_attendance_grid=Mock(),batch_attendance=Mock(),
            close_daily_attendance=Mock(),edit_selected_attendance=Mock(),
            employees=object())
        container=object()
        add=SimpleNamespace(master=container)
        shell=SimpleNamespace(pages={'Payroll':page},
            _first_button=Mock(return_value=add),_buttons=Mock(return_value=[]),
            _forget=Mock(),_action_menu=Mock(return_value=object()),
            _selection_controls=Mock())
        CleanContractorApp._clean_payroll(shell)
        attendance=[call for call in shell._action_menu.call_args_list
                    if call.args[1]=='Attendance Actions']
        self.assertEqual(len(attendance),1)
        entries=attendance[0].args[2]
        self.assertEqual(entries[0],('Batch attendance (weekly grid)',page.batch_attendance))
        self.assertEqual(len(entries),3)

    def test_real_clean_interface_exposes_grid_menu(self):
        fixture=ProjectFundingTests('test_funding_is_one_expense_two_linked_project_views')
        fixture.setUp()
        try:
            try:
                ui=CleanContractorApp(Path(fixture.folder.name)/'test.db')
            except tk.TclError:
                self.skipTest('Desktop display unavailable')
            try:
                ui.withdraw();ui.update_idletasks()
                control=ui._first_menubutton(ui.pages['Payroll'],'Attendance Actions')
                self.assertIsNotNone(control)
                menu=ui.nametowidget(control.cget('menu'))
                labels=[menu.entrycget(index,'label') for index in range(menu.index('end')+1)]
                self.assertEqual(labels[0],'Batch attendance (weekly grid)')
                self.assertNotIn('Single-day batch attendance (legacy)',labels)
            finally:
                ui.db.close();ui.destroy()
        finally:
            fixture.doCleanups()


if __name__=='__main__':unittest.main()
