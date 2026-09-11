#requires -Version 7.0
<#
.SYNOPSIS
Runs a bounded Hantek DSO5102P action or lists the offline control catalog.
.DESCRIPTION
Finds Python 3 and runs the client independently of the current directory.
Python selection: -PythonPath, HANTEK_PYTHON, installed python/python3,
the py -3 launcher, then the current user's bundled Codex Python runtime.
WindowsApps aliases are skipped. Invalid explicit runtime choices fail without
falling back. GUID selection: -InterfaceGuid, HANTEK_INTERFACE_GUID, default.
Captures and action logs default to this repository's artifacts directory.
Relative -OutputDir and -LogDir paths refer to the calling project's directory.
Acquisition actions affect the oscilloscope only, never a CNC machine.
.EXAMPLE
pwsh -File C:\Github\Hantek\scripts\scope.ps1 -Help
.EXAMPLE
pwsh -File C:\Github\Hantek\scripts\scope.ps1 screenshot -OutputDir .\measurements
.EXAMPLE
pwsh -File C:\Github\Hantek\scripts\scope.ps1 acquisition-stop -LogDir .\measurement-logs
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('identify', 'echo', 'screenshot', 'acquisition-start', 'acquisition-stop', 'controls', 'panel-control', 'read-settings')]
    [string]$Action,
    [Parameter(Position = 1)]
    [string]$Control,
    [ValidatePattern('^[1-5]$')]
    [string]$Count = '1',
    [string]$PythonPath,
    [string]$InterfaceGuid,
    [string]$OutputDir,
    [string]$LogDir,
    [Alias('h')]
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($Help) {
    Write-Output @"
Hantek DSO5102P scope client (PowerShell 7, Python 3.8+)

Usage: scope.ps1 <action> [options]
Actions: identify, echo, screenshot, acquisition-start, acquisition-stop
         controls (offline), panel-control, read-settings (raw SYSData)
Acquisition actions affect the oscilloscope only, never a CNC machine.
Panel actions are named ordinary gestures; inspect the screen to verify results.

-PythonPath       Python executable; overrides HANTEK_PYTHON and discovery.
-InterfaceGuid    WinUSB GUID; overrides HANTEK_INTERFACE_GUID and the default.
-OutputDir        Screenshot destination, otherwise artifacts/captures in this repo.
-LogDir           Acquisition, panel and settings records; otherwise artifacts/logs.
-Control          Named panel control; use controls to list IDs without accessing USB.
-Count            Panel rotary gestures 1..5; buttons accept exactly 1 (default).
-Help             Show this help without accessing USB.

Python discovery: configured path, installed python/python3, py -3, bundled
current-user Codex runtime. WindowsApps aliases are skipped.
Relative output paths refer to the calling project's current directory.

Example:
  pwsh -File '$PSCommandPath' screenshot -OutputDir .\measurements
  pwsh -File '$PSCommandPath' controls
  pwsh -File '$PSCommandPath' panel-control -Control ch1-scale-plus -Count 1
"@
    exit 0
}
if (-not $Action) {
    throw 'Specify a scope action or controls for the offline catalog. Use -Help for examples.'
}
if ($Action -eq 'panel-control') {
    if ([string]::IsNullOrWhiteSpace($Control)) { throw 'panel-control requires a named -Control. Use controls to list IDs.' }
} elseif ($PSBoundParameters.ContainsKey('Control') -or $PSBoundParameters.ContainsKey('Count')) {
    throw '-Control and -Count apply only to panel-control.'
}
if ($PSBoundParameters.ContainsKey('OutputDir') -and $Action -ne 'screenshot') {
    throw '-OutputDir applies only to screenshot.'
}
if ($PSBoundParameters.ContainsKey('LogDir') -and $Action -notin @('acquisition-start', 'acquisition-stop', 'panel-control', 'read-settings')) {
    throw '-LogDir applies only to acquisition, panel-control or read-settings actions.'
}
foreach ($directoryParameter in @('OutputDir', 'LogDir')) {
    if ($PSBoundParameters.ContainsKey($directoryParameter) -and
        [string]::IsNullOrWhiteSpace($PSBoundParameters[$directoryParameter])) {
        throw "-$directoryParameter must name an output directory."
    }
}

$scopeGuid = if ($PSBoundParameters.ContainsKey('InterfaceGuid')) {
    $InterfaceGuid
} elseif ($null -ne $env:HANTEK_INTERFACE_GUID) {
    $env:HANTEK_INTERFACE_GUID
} else {
    '5cb35641-beea-4a98-b06b-3cf4dca1911b'
}
$parsedScopeGuid = [guid]::Empty
if ($Action -ne 'controls' -and ([string]::IsNullOrWhiteSpace($scopeGuid) -or
    -not [guid]::TryParse($scopeGuid.Trim(), [ref]$parsedScopeGuid))) {
    throw 'Invalid interface GUID. Set -InterfaceGuid or HANTEK_INTERFACE_GUID to a valid GUID.'
}

function Test-PythonRuntime {
    param([string]$Candidate, [string[]]$PrefixArguments = @())
    if ($Candidate -match '(?i)(?:^|[\\/])WindowsApps(?:[\\/]|$)' -or
        -not (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
        return $false
    }
    try {
        $null = & $Candidate @PrefixArguments -c 'import sys; sys.exit(0 if sys.version_info.major == 3 and sys.version_info >= (3, 8) else 1)' 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Find-PythonRuntime {
    param([string]$ExplicitPath, [bool]$HasExplicitPath)
    if ($HasExplicitPath) {
        if ([string]::IsNullOrWhiteSpace($ExplicitPath)) {
            throw 'The configured Python path is empty; provide the path to a Python 3 executable.'
        }
        $resolvedPython = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ExplicitPath)
        if (-not (Test-PythonRuntime -Candidate $resolvedPython)) {
            throw "Configured Python is unavailable or unsupported: $resolvedPython. Use a real Python 3.8+ executable, not a WindowsApps alias."
        }
        return [pscustomobject]@{ Path = $resolvedPython; Prefix = @() }
    }
    foreach ($name in @('python.exe', 'python3.exe')) {
        foreach ($candidate in @(Get-Command -Name $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
            if (Test-PythonRuntime -Candidate $candidate.Source) {
                return [pscustomobject]@{ Path = $candidate.Source; Prefix = @() }
            }
        }
    }
    foreach ($candidate in @(Get-Command -Name 'py.exe' -CommandType Application -All -ErrorAction SilentlyContinue)) {
        if (Test-PythonRuntime -Candidate $candidate.Source -PrefixArguments @('-3')) {
            return [pscustomobject]@{ Path = $candidate.Source; Prefix = @('-3') }
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
        $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-PythonRuntime -Candidate $bundledPython) {
            return [pscustomobject]@{ Path = $bundledPython; Prefix = @() }
        }
    }
    throw 'No usable Python 3.8+ runtime was found. Set -PythonPath or HANTEK_PYTHON to a trusted Python executable.'
}

$hasConfiguredPython = $PSBoundParameters.ContainsKey('PythonPath') -or $null -ne $env:HANTEK_PYTHON
$configuredPython = if ($PSBoundParameters.ContainsKey('PythonPath')) { $PythonPath } else { $env:HANTEK_PYTHON }
$runtime = Find-PythonRuntime -ExplicitPath $configuredPython -HasExplicitPath $hasConfiguredPython
$scopeClient = Join-Path (Split-Path -Parent $PSScriptRoot) 'src\hantek_scope.py'
if (-not (Test-Path -LiteralPath $scopeClient -PathType Leaf)) {
    throw "Hantek client not found: $scopeClient"
}
$clientArguments = @($runtime.Prefix) + @($scopeClient)
if ($Action -ne 'controls') { $clientArguments += @('--guid', $parsedScopeGuid.ToString()) }
$clientArguments += @($Action)
if ($Action -eq 'panel-control') { $clientArguments += @($Control, '--count', [string]$Count) }
if ($PSBoundParameters.ContainsKey('OutputDir')) {
    $clientArguments += @('--output-dir', $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir))
}
if ($PSBoundParameters.ContainsKey('LogDir')) {
    $clientArguments += @('--log-dir', $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($LogDir))
}
& $runtime.Path @clientArguments
exit $LASTEXITCODE
