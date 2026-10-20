param(
    [Parameter(Mandatory=$true)][string]$Video,
    [string]$Output = (Join-Path $PSScriptRoot 'outputs\run'),
    [ValidateSet('hybrid','visual','audio','ball-motion')][string]$Mode = 'hybrid',
    [string]$Labels,
    [switch]$Preview,
    [switch]$ExportClips
)
$ErrorActionPreference = 'Stop'
$resolvedVideo = (Resolve-Path -LiteralPath $Video).Path
$resolvedLabels = if ($Labels) { (Resolve-Path -LiteralPath $Labels).Path } else { $null }
$resolvedOutput = [System.IO.Path]::GetFullPath($Output)
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run .\setup.ps1 first.' }
Write-Host 'Untrimmed training video baseline: results require manual validation.'
$parameters = @('-m','rallycut.cli','analyze',$resolvedVideo,'--mode',$Mode,'--threads','2','--output',$resolvedOutput)
if ($resolvedLabels) { $parameters += @('--labels',$resolvedLabels) }
if ($Preview) { $parameters += '--preview' }
if ($ExportClips) { $parameters += '--export-clips' }
& $python @parameters
if ($LASTEXITCODE -ne 0) { throw 'Video analysis failed.' }
Start-Process -FilePath (Join-Path $resolvedOutput 'review.html')
