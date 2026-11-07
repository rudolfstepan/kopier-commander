@echo off
setlocal
cd /d "%~dp0"
where pythonw.exe >nul 2>&1
if errorlevel 1 goto console
start "" pythonw.exe "%~dp0run.py" %*
exit /b
:console
python "%~dp0run.py" %*
if errorlevel 1 pause
