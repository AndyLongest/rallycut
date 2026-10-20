$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Creating the virtual environment failed.' }
}
& '.\.venv\Scripts\python.exe' -c "import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8, 'Use Python 3.12 x64 for the validated source setup'"
if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-runtime.txt -e '.[test]'
if ($LASTEXITCODE -ne 0) { throw 'Installing dependencies failed.' }
& '.\.venv\Scripts\python.exe' tools/bootstrap_upstream.py
if ($LASTEXITCODE -ne 0) { throw 'Upstream verification failed.' }
Write-Host 'RallyCut ready. Install FFmpeg/ffprobe on PATH, or copy runtime/ffmpeg from the Light release into this project. See docs/HANDOFF.md.'
