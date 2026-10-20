@echo off
setlocal
cd /d "%~dp0"
if not exist "data\logs" mkdir "data\logs"
if not exist "data\temp" mkdir "data\temp"
if not exist "data\cache" mkdir "data\cache"
set "TEMP=%CD%\data\temp"
set "TMP=%CD%\data\temp"
set "XDG_CACHE_HOME=%CD%\data\cache"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "PATH=%CD%\runtime\ffmpeg\bin;%SystemRoot%\System32;%SystemRoot%"
if not exist "runtime\python\python.exe" (
  echo Please extract the entire ZIP before starting RallyCut.
  pause
  exit /b 1
)
echo RallyCut is starting. Your browser will open automatically.
echo Keep this window open while processing videos.
echo To stop safely, double-click Stop.cmd in this folder.
"runtime\python\python.exe" -X utf8 -B -u -m rallycut.local_app --root "%CD%" --open >>"data\logs\launcher.log" 2>&1
if errorlevel 1 (
  echo RallyCut could not start. See data\logs\launcher.log
  type "data\logs\launcher.log"
  pause
  exit /b 1
)
