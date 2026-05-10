param(
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$component = Join-Path $repoRoot "custom_components/midea_ac_lan"
$outDir = Join-Path $repoRoot $OutputDir
$zip = Join-Path $outDir "midea_ac_lan.zip"

if (-not (Test-Path (Join-Path $component "manifest.json"))) {
    throw "Component directory not found: $component"
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
if (Test-Path $zip) {
    Remove-Item -LiteralPath $zip -Force
}

Compress-Archive -Path (Join-Path $component "*") -DestinationPath $zip
Get-Item $zip | Select-Object FullName, Length, LastWriteTime
