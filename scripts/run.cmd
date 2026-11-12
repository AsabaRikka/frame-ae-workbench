@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if exist "%~dp0..\.venv\Scripts\python.exe" goto root_venv
if exist "%~dp0..\ae_workbench\.venv\Scripts\python.exe" goto local_venv
py -3 -c "import sys;sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 goto python_launcher
python -c "import sys;sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 goto python_path
echo Python 3.10+ was not found. Install Python or activate the project environment.
pause
exit /b 1
:root_venv
"%~dp0..\.venv\Scripts\python.exe" "%~dp0launch.py" %*
goto finish
:local_venv
"%~dp0..\ae_workbench\.venv\Scripts\python.exe" "%~dp0launch.py" %*
goto finish
:python_launcher
py -3 "%~dp0launch.py" %*
goto finish
:python_path
python "%~dp0launch.py" %*
:finish
set "workbench_exit=%errorlevel%"
if not "%workbench_exit%"=="0" pause
exit /b %workbench_exit%
