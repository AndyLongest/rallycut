param(
    [Parameter(Mandatory=$true)][string]$Video,
    [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference = "Stop"
$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Project Python environment is missing. Run setup.ps1 first."
}
$mediaBin = Join-Path $PSScriptRoot "runtime\ffmpeg\bin"
if (Test-Path -LiteralPath $mediaBin) { $env:PATH = "$mediaBin;$env:PATH" }
& $pythonPath (Join-Path $PSScriptRoot "tools\run_fast_visual.py") $Video --output $Output
exit $LASTEXITCODE
