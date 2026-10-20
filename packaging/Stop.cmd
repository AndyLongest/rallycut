@echo off
setlocal
cd /d "%~dp0"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONDONTWRITEBYTECODE=1"
"runtime\python\python.exe" -X utf8 -B -m rallycut.local_app --root "%CD%" --stop
if errorlevel 1 (
  echo Unable to stop RallyCut. Check data\logs.
  pause
  exit /b 1
)
