#requires -Version 7.0
[CmdletBinding()]
param([switch]$Demo)
$ErrorActionPreference = 'Stop'
$scopeRepo = Split-Path -Parent $PSScriptRoot
$scopeVersion = (Get-Content -LiteralPath (Join-Path $scopeRepo 'desktop/package.json') -Raw | ConvertFrom-Json).version
$scopeProgram = Join-Path $scopeRepo "desktop/release/Hantek-Studio-$scopeVersion-Windows.exe"
if (-not (Test-Path -LiteralPath $scopeProgram -PathType Leaf)) { throw 'Build the app first with scripts/build-desktop.ps1.' }
# The user requested a visible standalone desktop program.
if ($Demo) { Start-Process -FilePath $scopeProgram -ArgumentList '--demo' }
else { Start-Process -FilePath $scopeProgram }
