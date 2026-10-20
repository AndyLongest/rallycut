@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.ps1 first. See docs\HANDOFF.md.
  pause
  exit /b 1
)
set "PATH=%CD%\runtime\ffmpeg\bin;%PATH%"
".venv\Scripts\python.exe" -X utf8 -m rallycut.local_app --open
if errorlevel 1 pause
