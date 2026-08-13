@echo off
cd /d "%~dp0"
python seed_project_oasis_employees.py "%~dp0contractor_tracker.db"
pause
