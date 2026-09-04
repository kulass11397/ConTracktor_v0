@echo off
setlocal
cd /d "%~dp0"

rem Keep the existing demo/client records in the database beside this launcher.
set "CONTRACTOR_DB_PATH=%~dp0contractor_tracker_demo.db"

set "PYTHON_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if exist "%~dp0..\..\.venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0..\..\.venv\Scripts\python.exe"

"%PYTHON_EXE%" "%~dp0app.py"
if errorlevel 1 pause
endlocal
