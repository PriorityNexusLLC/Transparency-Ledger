@echo off
rem MONTHLY (runs on the 1st): record last month's work across all Priority Nexus repos and reviewed reports,
rem write last month's summary, check the chain, and upload ONCE. Nothing is ever edited, only added.
cd /d "%~dp0"
set PATH=C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI;%PATH%
python -X utf8 ledger.py sync-git
python -X utf8 ledger.py sync-reports "%USERPROFILE%\PriorityNexus\data\reports"
for /f %%m in ('python -c "import datetime as d; t=d.date.today().replace(day=1)-d.timedelta(days=1); print(t.strftime('%%Y-%%m'))"') do set LAST=%%m
python -X utf8 ledger.py stats %LAST%
python -X utf8 ledger.py verify || (echo Chain check failed: nothing uploaded. & exit /b 1)
git add LEDGER.md STATS
git commit -q -m "Ledger: %LAST% summary"
git push -q
echo Done: %LAST% summary uploaded.
