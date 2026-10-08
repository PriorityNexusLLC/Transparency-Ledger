@echo off
rem MONTHLY (runs on the 1st): each project's own ledger records last month's work and is uploaded once; then the
rem monthly report for all projects is written here and uploaded once. Nothing is ever edited, only added.
cd /d "%~dp0"
set PATH=C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI;%PATH%
python -X utf8 ledger.py monthly
