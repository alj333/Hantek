#requires -Version 7.0
[CmdletBinding()]
param([string]$PythonPath = $env:HANTEK_PYTHON, [switch]$SkipInstall)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$scopeRepo = Split-Path -Parent $PSScriptRoot
$scopeDesktop = Join-Path $scopeRepo 'desktop'
$scopeBuild = Join-Path $scopeRepo '.local/build'
$scopeVenv = Join-Path $scopeRepo '.local/build-venv'
if (-not $PythonPath) {
    $scopeCandidates = @((Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'))
    $scopeCandidates += @(Get-Command python.exe -CommandType Application -All -ErrorAction SilentlyContinue | ForEach-Object Source)
    $PythonPath = $scopeCandidates | Where-Object { $_ -notmatch '[\\/]WindowsApps[\\/]' -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
}
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Set -PythonPath to a trusted Python 3.12 x64 executable.' }
$scopePythonCheck = & $PythonPath -c 'import struct,sys; print(sys.version); sys.exit(0 if sys.version_info >= (3, 12) and struct.calcsize("P") == 8 else 1)'
if ($LASTEXITCODE -ne 0) { throw 'The Windows build needs Python 3.12+ x64.' }
Write-Output $scopePythonCheck
$scopeNpm = (Get-Command npm.cmd -CommandType Application -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $scopeBuild -Force | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $scopeVenv 'Scripts/python.exe'))) {
    & $PythonPath -m venv $scopeVenv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated build environment.' }
}
$scopeBuildPython = Join-Path $scopeVenv 'Scripts/python.exe'
if (-not $SkipInstall) {
    & $scopeBuildPython -m pip install --disable-pip-version-check -r (Join-Path $scopeRepo 'requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
}
Push-Location $scopeRepo
try {
    & $scopeBuildPython -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Python checks failed.' }
    & $scopeBuildPython -m PyInstaller --noconfirm --clean --onedir --console --noupx --name scope-bridge --add-data "$(Join-Path $scopeRepo 'src/control_catalog.json');." --distpath $scopeBuild --workpath (Join-Path $scopeBuild 'pyinstaller-work') --specpath $scopeBuild (Join-Path $scopeRepo 'src/desktop_bridge.py')
    if ($LASTEXITCODE -ne 0) { throw 'Scope runtime packaging failed.' }
    $scopeFrozen = Join-Path $scopeBuild 'scope-bridge/scope-bridge.exe'
    $scopeSelfTestText = & $scopeFrozen --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Packaged runtime self-test failed.' }
    $scopeSelfTest = $scopeSelfTestText | ConvertFrom-Json
    if (-not $scopeSelfTest.ok -or $scopeSelfTest.result.protocol_version -ne 1 -or $scopeSelfTest.result.hardware_access -ne $false -or $scopeSelfTest.result.runtime.pointer_bits -ne 64 -or $scopeSelfTest.result.runtime.frozen -ne $true) { throw 'Packaged runtime did not pass its capability check.' }
    Write-Output $scopeSelfTestText
    # Preserve the Python interpreter's redistribution notice with the runtime.
    $scopeBasePrefix = & $scopeBuildPython -c 'import sys; print(sys.base_prefix)'
    $scopeLicense = Join-Path $scopeBasePrefix 'LICENSE.txt'
    if (Test-Path -LiteralPath $scopeLicense) { Copy-Item -LiteralPath $scopeLicense -Destination (Join-Path $scopeBuild 'scope-bridge/PYTHON-LICENSE.txt') }
    Set-Location $scopeDesktop
    if (-not $SkipInstall) {
        & $scopeNpm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Desktop dependency installation failed.' }
    }
    & $scopeNpm run build
    if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
    & $scopeNpm test
    if ($LASTEXITCODE -ne 0) { throw 'Desktop checks failed.' }
    & $scopeNpm run package:win
    if ($LASTEXITCODE -ne 0) { throw 'Windows package build failed.' }
    Write-Output 'Standalone Windows app is ready in desktop/release.'
} finally { Pop-Location }
