param(
    [Parameter(Mandatory=$true)][string]$Video,
    [switch]$ExportClips
)
$ErrorActionPreference = 'Stop'
Write-Warning 'Use run_video.ps1 for training footage. The old edit-boundary demo is not a rally recognition acceptance test.'
& (Join-Path $PSScriptRoot 'run_video.ps1') -Video $Video -Output (Join-Path $PSScriptRoot 'outputs\demo_candidates') -Preview -ExportClips:$ExportClips
