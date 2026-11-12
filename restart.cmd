@echo off
call "%~dp0ae_workbench\run.cmd" restart %*
exit /b %errorlevel%
