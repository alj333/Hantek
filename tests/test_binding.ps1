#requires -Version 7.0
<#
Offline regression checks for the binding helper's restart-verification behavior.
Run with 64-bit PowerShell 7. Every device probe below is synthetic. CompileOnly
loads the interop types and polling function without enumerating or changing
devices, writing registry values, or creating installation logs.
#>
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scopeHelperPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts/bind-winusb.ps1'
. $scopeHelperPath -CompileOnly

$scopeTestId = 'USB\VID_049F&PID_505A\OFFLINE-TEST'
$scopeReady = [pscustomobject]@{ InstanceId=$scopeTestId; Service='WinUSB'; Problem=0 }
$scopePassed = 0

function Assert-ScopeWaitFails {
    param(
        [Parameter(Mandatory)][scriptblock]$Probe,
        [Parameter(Mandatory)][string]$ExpectedMessage
    )
    $scopeObserved = $null
    try {
        Wait-ScopeAfterRestart -ExpectedInstanceId $scopeTestId -TimeoutMilliseconds 20 -Inspect $Probe | Out-Null
    } catch { $scopeObserved = $_.Exception.Message }
    if ($null -eq $scopeObserved -or $scopeObserved -notmatch $ExpectedMessage) {
        throw "Expected failure '$ExpectedMessage', got '$scopeObserved'."
    }
}

# A restart may temporarily remove the device, then expose its old service before
# WinUSB becomes ready. Both states must be allowed within the bounded interval.
$scopeQueue = [Collections.Generic.Queue[object]]::new()
$scopeQueue.Enqueue([HantekInboxWinUsb+DeviceCountException]::new(0))
$scopeQueue.Enqueue([pscustomobject]@{ InstanceId=$scopeTestId; Service='DSO505A'; Problem=39 })
$scopeQueue.Enqueue($scopeReady)
$scopeRecovered = Wait-ScopeAfterRestart -ExpectedInstanceId $scopeTestId -TimeoutMilliseconds 1500 -Inspect {
    $scopeNext = $scopeQueue.Dequeue()
    if ($scopeNext -is [Exception]) { throw $scopeNext }
    $scopeNext
}
if ($scopeRecovered.InstanceId -ne $scopeTestId -or $scopeRecovered.Service -ne 'WinUSB' -or $scopeRecovered.Problem -ne 0 -or $scopeQueue.Count -ne 0) {
    throw 'Transient absence and service recovery did not return the ready original device.'
}
$scopePassed++
Write-Output 'PASS: transient absence and old-service state recover to the original ready device.'

Assert-ScopeWaitFails -Probe { throw [HantekInboxWinUsb+DeviceCountException]::new(0) } -ExpectedMessage 'remained absent'
$scopePassed++
Write-Output 'PASS: persistent absence reaches the bounded deadline.'

$scopeProbeCounter = [pscustomobject]@{ Calls=0 }
Assert-ScopeWaitFails -Probe {
    $scopeProbeCounter.Calls++
    throw [HantekInboxWinUsb+DeviceCountException]::new(2)
} -ExpectedMessage 'found 2'
if ($scopeProbeCounter.Calls -ne 1) { throw 'Multiple matching devices were retried.' }
$scopePassed++
Write-Output 'PASS: multiple matching devices fail immediately.'

$scopeProbeCounter.Calls = 0
Assert-ScopeWaitFails -Probe {
    $scopeProbeCounter.Calls++
    [pscustomobject]@{ InstanceId='WRONG-INSTANCE'; Service='WinUSB'; Problem=0 }
} -ExpectedMessage 'instance changed'
if ($scopeProbeCounter.Calls -ne 1) { throw 'A changed device identity was retried.' }
$scopePassed++
Write-Output 'PASS: changed identity fails immediately.'

Assert-ScopeWaitFails -Probe {
    [pscustomobject]@{ InstanceId=$scopeTestId; Service='DSO505A'; Problem=0 }
} -ExpectedMessage 'did not reach'
$scopePassed++
Write-Output 'PASS: a persistent wrong service fails by the deadline.'

Assert-ScopeWaitFails -Probe {
    [pscustomobject]@{ InstanceId=$scopeTestId; Service='WinUSB'; Problem=39 }
} -ExpectedMessage 'did not reach'
$scopePassed++
Write-Output 'PASS: a persistent problem code fails by the deadline.'

$scopeProbeCounter.Calls = 0
Assert-ScopeWaitFails -Probe {
    $scopeProbeCounter.Calls++
    throw [UnauthorizedAccessException]::new('Synthetic access failure')
} -ExpectedMessage 'Synthetic access failure'
if ($scopeProbeCounter.Calls -ne 1) { throw 'An unrelated inspection error was retried.' }
$scopePassed++
Write-Output 'PASS: unrelated inspection errors fail immediately.'

Write-Output "Passed $scopePassed offline binding checks. No device calls, installation, restart, or registry operations were performed."
