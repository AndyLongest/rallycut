param(
    [Parameter(Mandatory=$true)][string]$Video,
    [Parameter(Mandatory=$true)][string]$Output,
    [ValidateSet("fast","full")][string]$Mode = "fast",
    [ValidateSet("global","regional")][string]$SceneProfile = "global"
)
$ErrorActionPreference = "Stop"
$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) { throw "Run setup.ps1 first." }
& $pythonPath (Join-Path $PSScriptRoot "tools\run_visual_union.py") $Video --output $Output --mode $Mode --scene-profile $SceneProfile
exit $LASTEXITCODE
