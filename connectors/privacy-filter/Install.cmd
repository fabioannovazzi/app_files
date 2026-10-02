@echo off
cd /d "%~dp0"
py -3.12 install.py --setup
if errorlevel 1 echo Setup failed. Check Python 3.12 and the error above.
pause
