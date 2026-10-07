import unittest
import tkinter as tk
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import test_project_funding as fixtures
from app import (build_expense_billing_context, build_expense_client_summary,
                 read_weekly_attendance_xlsx, write_weekly_attendance_xlsx,
                 WeeklyAttendanceGridDialog)


class WeeklyGridTests(unittest.TestCase):
    setUp=fixtures.ProjectFundingTests.setUp

    def add_employee(self,project_id,number,name,assignment_project=None,
                     effective_from='2026-01-01',effective_to=''):
        salt,digest=fixtures.hash_pin('0000')
        employee_id=self.db.execute("""INSERT INTO employees(project_id,employee_no,pin_salt,
            pin_hash,name,rate_cents,daily_rate_cents) VALUES(?,?,?,?,?,100000,100000)""",
            (project_id,number,salt,digest,name)).lastrowid
        if assignment_project:
            self.db.execute("""INSERT INTO employee_project_assignments(employee_id,project_id,
                effective_from,effective_to,daily_rate_cents) VALUES(?,?,?,?,100000)""",
                (employee_id,assignment_project,effective_from,effective_to))
        return employee_id

    def test_week_roster_uses_overlapping_site_enrollments(self):
        current=self.add_employee(self.oasis,'OASIS-2','Oasis Worker',self.oasis)
        ended=self.add_employee(self.oasis,'OLD-1','Former Oasis Worker',self.oasis,
                                effective_to='2026-09-13')
        starts_midweek=self.add_employee(self.third,'THIRD-2','Midweek Worker',self.third,
                                         effective_from='2026-09-16')
        self.assertIn(current,[row['id'] for row in
            self.db.employees_deployed_during(self.oasis,'2026-09-14','2026-09-20')])
        self.assertNotIn(ended,[row['id'] for row in
            self.db.employees_deployed_during(self.oasis,'2026-09-14','2026-09-20')])
        self.assertIn(starts_midweek,[row['id'] for row in
            self.db.employees_deployed_during(self.third,'2026-09-14','2026-09-20')])

    def test_draft_is_separate_then_finalizes_two_sites(self):
        cells={
            (self.employee,'2026-09-14',self.oasis):{'state':'Present','segments':[['08:00','12:00']]},
            (self.employee,'2026-09-14',self.grace):{'state':'Present','segments':[['13:00','17:00']]},
            (self.employee,'2026-09-15',self.oasis):{'state':'Absent','segments':[]},
        }
        self.assertEqual(self.db.save_weekly_attendance_draft('2026-09-14',cells),3)
        self.assertEqual(self.db.all('SELECT * FROM attendance'),[])
        self.assertEqual(self.db.weekly_attendance_draft('2026-09-14'),cells)
        self.assertEqual(self.db.finalize_weekly_attendance_draft('2026-09-14',
            {self.oasis:self.heads[0],self.grace:self.heads[1]}),2)
        self.assertEqual(len(self.db.all('SELECT * FROM attendance')),2)
        self.assertEqual(len(self.db.all('SELECT * FROM attendance_closure_batches')),2)
        self.assertEqual(len(self.db.all("SELECT * FROM weekly_attendance_marks WHERE state='Absent'")),1)
        self.assertEqual(self.db.weekly_attendance_draft('2026-09-14'),{})
        self.assertEqual(self.db.company_weekly_payroll_summary('2026-09-14')[0]['gross_cents'],100000)

    def test_overlapping_sites_rejected_without_partial_save(self):
        cells={(self.employee,'2026-09-14',self.oasis):{'state':'Present','segments':[['08:00','13:00']]},
               (self.employee,'2026-09-14',self.grace):{'state':'Present','segments':[['12:00','17:00']]}}
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            self.db.save_weekly_attendance_draft('2026-09-14',cells)
        self.assertEqual(self.db.weekly_attendance_draft('2026-09-14'),{})

    def test_existing_attendance_blocks_duplicate_weekly_grid_entry(self):
        self.db.record_batch_project_attendance([(self.employee,self.oasis,
            datetime(2026,9,14,8),datetime(2026,9,14,12))],self.heads[0])
        cells={(self.employee,'2026-09-14',self.grace):{'state':'Present','segments':[['11:00','17:00']]}}
        with self.assertRaisesRegex(ValueError,'overlapping recorded attendance'):
            self.db.save_weekly_attendance_draft('2026-09-14',cells)

    def workbook_inputs(self,extra_employee=None):
        projects=self.db.all("SELECT id,name FROM projects WHERE status<>'Completed' ORDER BY name")
        employees=self.db.all('SELECT id,name,employee_no FROM employees WHERE active=1 ORDER BY name')
        rosters={project['id']:{self.employee} for project in projects}
        if extra_employee:
            rosters[self.third].add(extra_employee)
        return projects,employees,rosters

    def rewrite_google_sheets_style(self,source,destination,project_id,row_number,employee_label,
                                    employee_no,value):
        with zipfile.ZipFile(source) as archive:
            members={name:archive.read(name) for name in archive.namelist()}
        target_name=None
        for name,content in members.items():
            if not name.startswith('xl/worksheets/') or not name.endswith('.xml'):
                continue
            text=content.decode('utf-8')
            if re.search(rf'<c r="B3"[^>]*>.*?<t>{project_id}</t>',text,re.S):
                target_name=name
                break
        self.assertIsNotNone(target_name)
        text=members[target_name].decode('utf-8')
        replacements={'A':employee_label,'B':employee_no,'C':value}
        for column,replacement in replacements.items():
            text=re.sub(
                rf'(<c r="{column}{row_number}"[^>]*>.*?<t>).*?(</t>)',
                lambda match:match.group(1)+replacement+match.group(2),text,count=1,flags=re.S)
        text=re.sub(r'<dataValidations.*?</dataValidations>','',text,flags=re.S)
        text=re.sub(r'<conditionalFormatting.*?</conditionalFormatting>','',text,flags=re.S)
        members[target_name]=text.encode('utf-8')
        workbook=members['xl/workbook.xml'].decode('utf-8')
        workbook=workbook.replace('name="Oasis"','name="Renamed in Google Sheets"')
        members['xl/workbook.xml']=workbook.encode('utf-8')
        with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
            for name in reversed(list(members)):
                archive.writestr(name,members[name])

    def test_attendance_workbook_round_trip_and_google_sheets_rewrite(self):
        extra=self.add_employee(self.third,'EXTRA-1','Additional Worker',self.third)
        projects,employees,rosters=self.workbook_inputs(extra)
        cells={
            (self.employee,'2026-09-12',self.oasis):{'state':'Present','segments':[['08:00','17:00']]},
            (self.employee,'2026-09-13',self.grace):{'state':'Absent','segments':[]},
            (self.employee,'2026-09-14',self.third):{'state':'Present','segments':[['08:00','12:00'],['13:00','15:30']]},
        }
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'generated.xlsx'
            shared=Path(folder)/'google-sheets-export.xlsx'
            write_weekly_attendance_xlsx(source,'2026-09-14',projects,employees,rosters,cells)
            result=read_weekly_attendance_xlsx(source,'2026-09-14',projects,employees,
                expected_project_ids=set(self.projects))
            self.assertEqual(result['cells'],cells)
            self.rewrite_google_sheets_style(source,shared,self.oasis,12,
                'Additional Worker [EXTRA-1]','EXTRA-1','P')
            result=read_weekly_attendance_xlsx(shared,'2026-09-14',projects,employees,
                expected_project_ids=set(self.projects))
            self.assertEqual(result['cells'][(extra,'2026-09-12',self.oasis)],
                             {'state':'Present','segments':[['08:00','17:00']]})
            self.assertIn(extra,result['project_employee_ids'][self.oasis])

    def test_attendance_workbook_styles_follow_excel_schema_order(self):
        projects,employees,rosters=self.workbook_inputs()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'generated.xlsx'
            write_weekly_attendance_xlsx(path,'2026-09-14',projects,employees,rosters,{})
            with zipfile.ZipFile(path) as archive:
                styles=ET.fromstring(archive.read('xl/styles.xml'))
                worksheet_names=[name for name in archive.namelist()
                                 if name.startswith('xl/worksheets/sheet') and name.endswith('.xml')]
                worksheets=[ET.fromstring(archive.read(name)) for name in worksheet_names]
        local_names=[node.tag.rsplit('}',1)[-1] for node in styles]
        style_sequence=['fonts','fills','borders','cellStyleXfs','cellXfs','cellStyles','dxfs']
        self.assertEqual([name for name in local_names if name in style_sequence],style_sequence)
        namespace='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        cell_xfs=styles.find(namespace+'cellXfs')
        dxfs=styles.find(namespace+'dxfs')
        self.assertEqual(int(cell_xfs.attrib['count']),len(cell_xfs))
        self.assertEqual(int(dxfs.attrib['count']),len(dxfs))
        for differential_style in dxfs:
            self.assertEqual([node.tag.rsplit('}',1)[-1] for node in differential_style],
                             ['font','fill'])
        for worksheet in worksheets:
            for cell in worksheet.findall('.//'+namespace+'c'):
                if 's' in cell.attrib:
                    self.assertLess(int(cell.attrib['s']),len(cell_xfs))
            for rule in worksheet.findall('.//'+namespace+'cfRule'):
                if 'dxfId' in rule.attrib:
                    self.assertLess(int(rule.attrib['dxfId']),len(dxfs))

    def test_attendance_workbook_rejects_changed_recorded_cell(self):
        projects,employees,rosters=self.workbook_inputs()
        key=(self.employee,'2026-09-12',self.oasis)
        recorded={key:[{'clock_in':'2026-09-12T08:00:00','clock_out':'2026-09-12T17:00:00',
                        'payroll_batch_id':None}]}
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'generated.xlsx'
            changed=Path(folder)/'changed.xlsx'
            write_weekly_attendance_xlsx(source,'2026-09-14',projects,employees,rosters,{},recorded)
            self.rewrite_google_sheets_style(source,changed,self.oasis,11,
                'Worker [EMP1]','EMP1','P')
            with self.assertRaisesRegex(ValueError,'was changed or removed'):
                read_weekly_attendance_xlsx(changed,'2026-09-14',projects,employees,recorded,
                    expected_project_ids=set(self.projects))

    def test_attendance_workbook_import_validation_is_atomic(self):
        extra=self.add_employee(self.third,'EXTRA-2','Overlap Worker',self.third)
        projects,employees,rosters=self.workbook_inputs(extra)
        cells={
            (extra,'2026-09-12',self.oasis):{'state':'Present','segments':[['08:00','13:00']]},
            (extra,'2026-09-12',self.third):{'state':'Present','segments':[['12:00','17:00']]},
        }
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'overlap.xlsx'
            rosters[self.oasis].add(extra)
            write_weekly_attendance_xlsx(path,'2026-09-14',projects,employees,rosters,cells)
            imported=read_weekly_attendance_xlsx(path,'2026-09-14',projects,employees,
                expected_project_ids=set(self.projects))
            with self.assertRaisesRegex(ValueError,'Overlapping'):
                self.db._validated_weekly_cells('2026-09-14',imported['cells'])
            self.assertEqual(self.db.weekly_attendance_draft('2026-09-14'),{})

    def test_billing_math_is_read_only(self):
        self.db.execute("INSERT INTO expenses(project_id,name,total_cents,expense_date) VALUES(?,'Material',12345,'2026-09-14')",(self.oasis,))
        rows=self.db.all("""SELECT e.*,'' phase,0 payment_total,0 recovery_total,0 cash_advance_id
            FROM expenses e WHERE e.project_id=?""",(self.oasis,))
        before=self.db.conn.total_changes
        context=build_expense_client_summary(self.db,rows,[self.oasis],date_from='2026-09-12',date_to='2026-09-18')
        bill=build_expense_billing_context(self.db,rows,context,'15','Client','Biller')
        self.assertEqual(bill['basis_cents'],12345)
        self.assertEqual(bill['fee_cents'],1852)
        self.assertEqual(bill['reimbursement_cents'],0)
        self.assertEqual(bill['amount_due_cents'],1852)
        self.assertEqual(bill['overall_cents'],1852)
        self.assertEqual(sum(context['weekly']['2026-09-12 to 2026-09-18'].values()),12345)
        self.assertEqual(self.db.conn.total_changes,before)

    def test_project_tabs_and_company_review_open(self):
        additional=self.add_employee(self.third,'THIRD-ONLY','Third Site Worker',self.third)
        try:
            root=tk.Tk()
        except tk.TclError:
            self.skipTest('Desktop display unavailable')
        root.withdraw()
        try:
            pane=WeeklyAttendanceGridDialog(root,self.db,root,'2026-09-14')
            root.update()
            self.assertEqual(len(pane.trees),4)
            self.assertIn(None,pane.trees)
            self.assertEqual(len(pane.trees[self.oasis].get_children()),1)
            self.assertNotIn(str(additional),pane.trees[self.oasis].get_children())
            self.assertIn(str(additional),pane.trees[self.third].get_children())
            self.assertTrue(pane.add_employee_to_project(self.oasis,additional))
            self.assertIn(str(additional),pane.trees[self.oasis].get_children())
            self.assertIn(str(additional),pane.trees[None].get_children())
            self.assertEqual(self.db.one("""SELECT COUNT(*) n FROM employee_project_assignments
                WHERE employee_id=? AND project_id=?""",(additional,self.oasis))['n'],0)
            pane.destroy()
        finally:
            root.destroy()


if __name__=='__main__':unittest.main()
