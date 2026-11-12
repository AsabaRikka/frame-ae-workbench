@echo off
call "%~dp0ae_workbench\run.cmd" start %*
exit /b %errorlevel%
