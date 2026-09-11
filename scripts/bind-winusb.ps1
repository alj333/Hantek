#requires -Version 7.0
<#
Run with 64-bit PowerShell 7. This helper does not change execution policy.
Default: read-only device/driver preflight. -CompileOnly compiles/checks interop only.
-Apply: bind the one present, exact Hantek USB device to the existing Microsoft
WinUSB model, then add a per-device interface GUID. Does not elevate itself.
-RestartDevice with -Apply: restart only that device using signed system PnPUtil.
-StateDirectory: backup/transcript directory; defaults to repository .local/setup.
-InterfaceGuid: GUID to register only when no valid interface GUID is already set.
No INF modification, driver download, certificate, security-policy, firmware,
USB-protocol, PC-restart, or machine-control operation is included.

Microsoft API references:
https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/winusb-installation
https://learn.microsoft.com/en-us/windows/win32/api/setupapi/nf-setupapi-setupdibuilddriverinfolist
https://learn.microsoft.com/en-us/windows/win32/api/setupapi/nf-setupapi-setupdiopendeviceinfow
https://learn.microsoft.com/en-us/windows/win32/api/setupapi/nf-setupapi-setupdisetselecteddriverw
https://learn.microsoft.com/en-us/windows/win32/api/newdev/nf-newdev-diinstalldevice
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$CompileOnly,
    [switch]$RestartDevice,
    [ValidateNotNullOrEmpty()]
    [string]$StateDirectory = (Join-Path (Split-Path -Parent $PSScriptRoot) '.local/setup'),
    [Guid]$InterfaceGuid = '5cb35641-beea-4a98-b06b-3cf4dca1911b'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($Apply -and $CompileOnly) { throw 'Choose -Apply or -CompileOnly, not both.' }
if ($RestartDevice -and -not $Apply) { throw '-RestartDevice requires -Apply.' }
if (-not [Environment]::Is64BitProcess) { throw 'Run from 64-bit PowerShell.' }
if ($InterfaceGuid -eq [Guid]::Empty) { throw '-InterfaceGuid must not be the empty GUID.' }

$scopeNativeSource = @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

public static class HantekInboxWinUsb {
  const uint PRESENT=2, ALLCLASSES=4, CLASSDRIVER=1, ENUMSINGLEINF=0x10000;
  const uint ALLOWEXCLUDED=0x800, INHERIT_CLASSDRVS=2;
  const int NO_MORE_ITEMS=259, INSUFFICIENT_BUFFER=122;
  const string HardwareId="USB\\VID_049F&PID_505A";
  static readonly IntPtr Invalid=new IntPtr(-1);

  [StructLayout(LayoutKind.Sequential)] public struct DevInfo {
    public uint cbSize; public Guid ClassGuid; public uint DevInst; public UIntPtr Reserved;
  }
  [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] public struct InstallParams {
    public uint cbSize, Flags, FlagsEx;
    public IntPtr hwndParent, InstallMsgHandler, InstallMsgHandlerContext, FileQueue;
    public UIntPtr ClassInstallReserved; public uint Reserved;
    [MarshalAs(UnmanagedType.ByValTStr,SizeConst=260)] public string DriverPath;
  }
  [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] public struct DriverInfo {
    public uint cbSize, DriverType; public UIntPtr Reserved;
    [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)] public string Description;
    [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)] public string MfgName;
    [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)] public string ProviderName;
    public System.Runtime.InteropServices.ComTypes.FILETIME DriverDate;
    public ulong DriverVersion;
  }
  [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] public struct DriverDetail {
    public uint cbSize; public System.Runtime.InteropServices.ComTypes.FILETIME InfDate;
    public uint CompatIDsOffset, CompatIDsLength; public UIntPtr Reserved;
    [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)] public string SectionName;
    [MarshalAs(UnmanagedType.ByValTStr,SizeConst=260)] public string InfFileName;
    [MarshalAs(UnmanagedType.ByValTStr,SizeConst=256)] public string DrvDescription;
    public ushort HardwareID;
  }
  public sealed class Report {
    public string InstanceId, HardwareIds, OriginalClassGuid, Service, DriverKey;
    public string CandidateInf, CandidateSection, CandidateProvider, CandidateDescription;
    public bool Installed, NeedReboot; public uint Status, Problem;
  }
  public sealed class DeviceCountException : InvalidOperationException {
    public int Count { get; private set; }
    public DeviceCountException(int count) : base("Expected exactly one present USB\\VID_049F&PID_505A device; found "+count+".") { Count=count; }
  }

  [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern IntPtr SetupDiGetClassDevsW(IntPtr cls,string enumerator,IntPtr parent,uint flags);
  [DllImport("setupapi.dll",SetLastError=true)]
  static extern IntPtr SetupDiCreateDeviceInfoList(IntPtr cls,IntPtr parent);
  [DllImport("setupapi.dll",SetLastError=true)]
  static extern bool SetupDiEnumDeviceInfo(IntPtr set,uint index,ref DevInfo dev);
  [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern bool SetupDiGetDeviceInstanceIdW(IntPtr set,ref DevInfo dev,StringBuilder id,uint size,out uint required);
  [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern bool SetupDiGetDeviceRegistryPropertyW(IntPtr set,ref DevInfo dev,uint prop,out uint type,byte[] buffer,uint size,out uint required);
  [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern bool SetupDiGetDeviceInstallParamsW(IntPtr set,IntPtr dev,ref InstallParams parms);
  [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern bool SetupDiSetDeviceInstallParamsW(IntPtr set,IntPtr dev,ref InstallParams parms);
  [DllImport("setupapi.dll",SetLastError=true)]
  static extern bool SetupDiBuildDriverInfoList(IntPtr set,IntPtr dev,uint type);
  [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern bool SetupDiOpenDeviceInfoW(IntPtr set,string id,IntPtr parent,uint flags,ref DevInfo dev);
  [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern bool SetupDiEnumDriverInfoW(IntPtr set,ref DevInfo dev,uint type,uint index,ref DriverInfo driver);
  [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern bool SetupDiGetDriverInfoDetailW(IntPtr set,ref DevInfo dev,ref DriverInfo driver,ref DriverDetail detail,uint size,out uint required);
  [DllImport("setupapi.dll",CharSet=CharSet.Unicode,SetLastError=true)]
  static extern bool SetupDiSetSelectedDriverW(IntPtr set,ref DevInfo dev,ref DriverInfo driver);
  [DllImport("setupapi.dll",SetLastError=true)]
  static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);
  [DllImport("newdev.dll",SetLastError=true)]
  static extern bool DiInstallDevice(IntPtr parent,IntPtr set,ref DevInfo dev,ref DriverInfo driver,uint flags,[MarshalAs(UnmanagedType.Bool)] out bool reboot);
  [DllImport("cfgmgr32.dll")]
  static extern uint CM_Get_DevNode_Status(out uint status,out uint problem,uint devInst,uint flags);

  static DevInfo NewDev(){ DevInfo d=new DevInfo(); d.cbSize=(uint)Marshal.SizeOf(typeof(DevInfo)); return d; }
  static DriverInfo NewDriver(){ DriverInfo d=new DriverInfo(); d.cbSize=(uint)Marshal.SizeOf(typeof(DriverInfo)); return d; }
  static void Check(bool ok,string operation){ if(!ok) throw new Win32Exception(Marshal.GetLastWin32Error(),operation); }
  static string Id(IntPtr set,ref DevInfo d){ uint n; StringBuilder s=new StringBuilder(4096); Check(SetupDiGetDeviceInstanceIdW(set,ref d,s,4096,out n),"Get device instance ID"); return s.ToString(); }
  static string Property(IntPtr set,ref DevInfo d,uint prop,bool required){
    uint type,n; byte[] b=new byte[16384];
    if(!SetupDiGetDeviceRegistryPropertyW(set,ref d,prop,out type,b,(uint)b.Length,out n)){
      int e=Marshal.GetLastWin32Error(); if(!required && (e==13 || e==2)) return null;
      throw new Win32Exception(e,"Read device property "+prop);
    }
    if(type!=1 && type!=7) throw new InvalidOperationException("Unexpected registry property type "+type);
    return Encoding.Unicode.GetString(b,0,(int)n).TrimEnd('\0');
  }
  static void AssertHardware(IntPtr set,ref DevInfo d){
    string id=Id(set,ref d);
    if(!id.StartsWith(HardwareId+"\\",StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Wrong device instance.");
    string ids=Property(set,ref d,1,true);
    bool exact=false; foreach(string h in ids.Split('\0')) if(String.Equals(h,HardwareId,StringComparison.OrdinalIgnoreCase)) exact=true;
    if(!exact) throw new InvalidOperationException("Exact hardware ID is absent.");
  }
  public static string[] ValidateSizes(){
    Type[] types={typeof(DevInfo),typeof(InstallParams),typeof(DriverInfo),typeof(DriverDetail)};
    int[] expected={32,584,1568,1584}; string[] result=new string[4];
    if(IntPtr.Size!=8) throw new InvalidOperationException("64-bit process required.");
    for(int i=0;i<types.Length;i++){ int n=Marshal.SizeOf(types[i]); if(n!=expected[i]) throw new InvalidOperationException("Unexpected size for "+types[i].Name+": "+n); result[i]=types[i].Name+"="+n; }
    return result;
  }
  public static Report InspectDevice(){
    IntPtr set=SetupDiGetClassDevsW(IntPtr.Zero,"USB",IntPtr.Zero,PRESENT|ALLCLASSES);
    if(set==Invalid) throw new Win32Exception(Marshal.GetLastWin32Error(),"Enumerate present USB devices");
    try{
      List<Report> matches=new List<Report>();
      for(uint i=0;;i++){
        DevInfo d=NewDev(); if(!SetupDiEnumDeviceInfo(set,i,ref d)){ int e=Marshal.GetLastWin32Error(); if(e==NO_MORE_ITEMS) break; throw new Win32Exception(e); }
        string id=Id(set,ref d); if(!id.StartsWith(HardwareId+"\\",StringComparison.OrdinalIgnoreCase)) continue;
        AssertHardware(set,ref d); Report r=new Report(); r.InstanceId=id; r.HardwareIds=Property(set,ref d,1,true).Replace('\0',';');
        r.OriginalClassGuid=d.ClassGuid.ToString("B"); r.Service=Property(set,ref d,4,false); r.DriverKey=Property(set,ref d,9,false);
        uint cr=CM_Get_DevNode_Status(out r.Status,out r.Problem,d.DevInst,0); if(cr!=0) throw new InvalidOperationException("CM_Get_DevNode_Status: "+cr);
        matches.Add(r);
      }
      if(matches.Count!=1) throw new DeviceCountException(matches.Count);
      return matches[0];
    } finally { SetupDiDestroyDeviceInfoList(set); }
  }
  public static Report Run(string expectedInstance,bool apply){
    ValidateSizes(); Report report=InspectDevice();
    if(!String.Equals(report.InstanceId,expectedInstance,StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Device identity changed since preflight.");
    string inf=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"INF","winusb.inf");
    if(!File.Exists(inf)) throw new FileNotFoundException("Inbox winusb.inf is missing.",inf);
    IntPtr set=SetupDiCreateDeviceInfoList(IntPtr.Zero,IntPtr.Zero);
    if(set==Invalid) throw new Win32Exception(Marshal.GetLastWin32Error(),"Create class-neutral information set");
    try {
      InstallParams p=new InstallParams(); p.cbSize=(uint)Marshal.SizeOf(typeof(InstallParams));
      Check(SetupDiGetDeviceInstallParamsW(set,IntPtr.Zero,ref p),"Get global install parameters");
      p.Flags|=ENUMSINGLEINF; p.FlagsEx|=ALLOWEXCLUDED; p.DriverPath=inf;
      Check(SetupDiSetDeviceInstallParamsW(set,IntPtr.Zero,ref p),"Restrict driver search to inbox winusb.inf");
      Check(SetupDiBuildDriverInfoList(set,IntPtr.Zero,CLASSDRIVER),"Build single-INF global driver list");
      DevInfo dev=NewDev();
      Check(SetupDiOpenDeviceInfoW(set,report.InstanceId,IntPtr.Zero,INHERIT_CLASSDRVS,ref dev),"Open exact device and inherit global class driver list");
      AssertHardware(set,ref dev);
      DriverInfo chosen=NewDriver(); int count=0;
      for(uint i=0;;i++){
        DriverInfo driver=NewDriver();
        if(!SetupDiEnumDriverInfoW(set,ref dev,CLASSDRIVER,i,ref driver)){ int e=Marshal.GetLastWin32Error(); if(e==NO_MORE_ITEMS) break; throw new Win32Exception(e,"Enumerate inherited drivers"); }
        DriverDetail detail=new DriverDetail(); detail.cbSize=(uint)Marshal.SizeOf(typeof(DriverDetail)); uint n;
        bool ok=SetupDiGetDriverInfoDetailW(set,ref dev,ref driver,ref detail,detail.cbSize,out n);
        if(!ok && Marshal.GetLastWin32Error()!=INSUFFICIENT_BUFFER) throw new Win32Exception(Marshal.GetLastWin32Error(),"Read candidate INF and section");
        if(!String.Equals(Path.GetFullPath(detail.InfFileName),Path.GetFullPath(inf),StringComparison.OrdinalIgnoreCase)) continue;
        if(!String.Equals(detail.SectionName,"WINUSB",StringComparison.OrdinalIgnoreCase)) continue;
        if(!String.Equals(driver.ProviderName,"Microsoft",StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Unexpected WinUSB provider.");
        chosen=driver; count++; report.CandidateInf=detail.InfFileName; report.CandidateSection=detail.SectionName;
        report.CandidateProvider=driver.ProviderName; report.CandidateDescription=driver.Description;
      }
      if(count!=1) throw new InvalidOperationException("Expected exactly one Microsoft WINUSB model in inbox winusb.inf; found "+count+".");
      if(!apply) return report;
      Report last=InspectDevice();
      if(!String.Equals(last.InstanceId,expectedInstance,StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Device identity changed before installation.");
      AssertHardware(set,ref dev);
      // MUTATION BOUNDARY: selecting a driver can update the device setup class.
      Check(SetupDiSetSelectedDriverW(set,ref dev,ref chosen),"Select exact inbox WINUSB model");
      bool reboot;
      Check(DiInstallDevice(IntPtr.Zero,set,ref dev,ref chosen,0,out reboot),"Install selected inbox WINUSB driver");
      report.Installed=true; report.NeedReboot=reboot;
      Report after=InspectDevice(); report.Service=after.Service; report.Status=after.Status; report.Problem=after.Problem;
      if(!String.Equals(after.Service,"WinUSB",StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Installer returned success, but device service is not WinUSB. Inspect setupapi.dev.log and saved backup.");
      return report;
    } finally { SetupDiDestroyDeviceInfoList(set); }
  }
}
'@

if (-not ('HantekInboxWinUsb' -as [type])) { Add-Type -TypeDefinition $scopeNativeSource -Language CSharp }
function Wait-ScopeAfterRestart {
    param(
        [Parameter(Mandatory)][string]$ExpectedInstanceId,
        [ValidateRange(1,30000)][int]$TimeoutMilliseconds = 5000,
        [scriptblock]$Inspect = { [HantekInboxWinUsb]::InspectDevice() }
    )
    $scopeDeadline = [Diagnostics.Stopwatch]::StartNew()
    $scopeLastReport = $null
    try {
        while ($true) {
            try { $scopeLastReport = & $Inspect }
            catch {
                $scopeCountError = $_.Exception
                while ($null -ne $scopeCountError -and $scopeCountError -isnot [HantekInboxWinUsb+DeviceCountException]) {
                    $scopeCountError = $scopeCountError.InnerException
                }
                # Only disappearance of this device is an expected restart transient.
                # Multiple devices, access errors, malformed properties, etc. fail now.
                if ($null -eq $scopeCountError -or $scopeCountError.Count -ne 0) { throw }
                $scopeLastReport = $null
            }
            if ($null -ne $scopeLastReport) {
                if ($scopeLastReport.InstanceId -ne $ExpectedInstanceId) { throw 'Device instance changed after restart.' }
                if ($scopeLastReport.Service -eq 'WinUSB' -and $scopeLastReport.Problem -eq 0) { return $scopeLastReport }
            }
            $scopeRemaining = $TimeoutMilliseconds - $scopeDeadline.ElapsedMilliseconds
            if ($scopeRemaining -le 0) { break }
            Start-Sleep -Milliseconds ([int][Math]::Min(200, $scopeRemaining))
        }
        if ($null -eq $scopeLastReport) { throw 'Scope remained absent after the bounded device-restart verification deadline.' }
        throw "Scope returned after restart but did not reach WinUSB/problem zero before the deadline (service=$($scopeLastReport.Service), problem=$($scopeLastReport.Problem))."
    } finally { $scopeDeadline.Stop() }
}
[HantekInboxWinUsb]::ValidateSizes() | Write-Output
if ($CompileOnly) { return }
$scopeBefore = [HantekInboxWinUsb]::InspectDevice()
$scopePreflight = [HantekInboxWinUsb]::Run($scopeBefore.InstanceId, $false)
$scopePreflight | Format-List
if (-not $Apply) {
    Write-Output 'Preflight only: no driver selection, binding, registry write, restart, or USB protocol call performed.'
    return
}

$scopeIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$scopePrincipal = New-Object Security.Principal.WindowsPrincipal($scopeIdentity)
if (-not $scopePrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw '-Apply requires an already elevated 64-bit PowerShell process.' }
$scopeGuardBefore = Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard
if (@($scopeGuardBefore.SecurityServicesRunning) -notcontains 2) { throw 'Memory integrity is not reported running. No installation attempted.' }
$scopePnpUtil = Join-Path ([Environment]::GetFolderPath('System')) 'pnputil.exe'
if ($RestartDevice) {
    $scopePnpSignature = Get-AuthenticodeSignature -LiteralPath $scopePnpUtil
    if ($scopePnpSignature.Status -ne 'Valid' -or $null -eq $scopePnpSignature.SignerCertificate -or $scopePnpSignature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
        throw 'System PnPUtil does not have a valid Microsoft signature. No installation attempted.'
    }
}

$scopeStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$scopeStatePath = [IO.Path]::GetFullPath($StateDirectory)
[IO.Directory]::CreateDirectory($scopeStatePath) | Out-Null
$scopeLog = Join-Path $scopeStatePath "winusb-binding-$scopeStamp.log"
$scopeBackupPath = Join-Path $scopeStatePath "winusb-binding-$scopeStamp-before.json"
$scopeDeviceKeyPath = 'SYSTEM\CurrentControlSet\Enum\' + $scopeBefore.InstanceId
$scopeParamsPath = $scopeDeviceKeyPath + '\Device Parameters'
$scopeOldValues = @()
$scopeReg = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($scopeParamsPath, $false)
if ($null -ne $scopeReg) {
    try {
        foreach ($scopeValueName in @('DeviceInterfaceGUID', 'DeviceInterfaceGUIDs')) {
            if ($scopeReg.GetValueNames() -contains $scopeValueName) {
                $scopeOldValues += [pscustomobject]@{ Name=$scopeValueName; Kind=$scopeReg.GetValueKind($scopeValueName).ToString(); Value=$scopeReg.GetValue($scopeValueName) }
            }
        }
    } finally { $scopeReg.Dispose() }
}
$scopeDriverData = $null
if ($scopeBefore.DriverKey) {
    $scopeDriverReg = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey(('SYSTEM\CurrentControlSet\Control\Class\' + $scopeBefore.DriverKey), $false)
    if ($null -ne $scopeDriverReg) {
        try { $scopeDriverData = [ordered]@{ InfPath=$scopeDriverReg.GetValue('InfPath'); InfSection=$scopeDriverReg.GetValue('InfSection'); ProviderName=$scopeDriverReg.GetValue('ProviderName'); DriverVersion=$scopeDriverReg.GetValue('DriverVersion') } }
        finally { $scopeDriverReg.Dispose() }
    }
}
$scopeBackup = [ordered]@{
    Time=(Get-Date).ToString('o'); Device=$scopeBefore; Candidate=$scopePreflight; PreviousDriver=$scopeDriverData
    DeviceParametersKey=$scopeParamsPath; PreviousInterfaceValues=$scopeOldValues
    MemoryIntegrityRunning=$true
    Rollback='For this saved instance only, use Device Manager > Update driver > Browse > Let me pick > Have Disk and select the original INF recorded above. Do not delete any driver packages. Restore only the two saved interface values to their prior state (remove only a newly added GUID). The old Cypress driver remains incompatible with Memory Integrity; restoring it does not repair that incompatibility.'
}
$scopeBackup | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $scopeBackupPath -Encoding UTF8
Start-Transcript -LiteralPath $scopeLog | Out-Null
try {
    Write-Output "Backup: $scopeBackupPath"
    Write-Output "Installing Microsoft inbox WinUSB on $($scopeBefore.InstanceId) only."
    $scopeResult = [HantekInboxWinUsb]::Run($scopeBefore.InstanceId, $true)
    $scopeResult | Format-List
    # Preserve an existing valid interface GUID; add a generated one only if needed.
    $scopeExistingGuids = @()
    foreach ($scopeOld in $scopeOldValues) {
        foreach ($scopeText in @($scopeOld.Value)) {
            $scopeParsed = [Guid]::Empty
            if ([Guid]::TryParse([string]$scopeText, [ref]$scopeParsed) -and $scopeParsed -ne [Guid]::Empty) { $scopeExistingGuids += $scopeParsed.ToString('B') }
        }
    }
    if ($scopeExistingGuids.Count -eq 0) {
        if ($scopeOldValues.Count -ne 0) { throw 'Existing interface registry values are invalid. Driver is bound; no interface value overwritten. Inspect backup.' }
        $scopeInterfaceGuid = $InterfaceGuid.ToString('B')
        $scopeReg = [Microsoft.Win32.Registry]::LocalMachine.CreateSubKey($scopeParamsPath, $true)
        try { $scopeReg.SetValue('DeviceInterfaceGUIDs', [string[]]@($scopeInterfaceGuid), [Microsoft.Win32.RegistryValueKind]::MultiString) }
        finally { $scopeReg.Dispose() }
        Write-Output "Added interface GUID: $scopeInterfaceGuid"
        if (-not $RestartDevice) { Write-Output 'Disconnect and reconnect the scope USB cable to the same port to register the interface. No automatic restart was performed.' }
    } else { Write-Output ('Preserved existing interface GUID(s): ' + ($scopeExistingGuids -join ', ')) }
    if ($RestartDevice) {
        $scopeCheckBeforeRestart = [HantekInboxWinUsb]::InspectDevice()
        if ($scopeCheckBeforeRestart.InstanceId -ne $scopeBefore.InstanceId -or $scopeCheckBeforeRestart.Service -ne 'WinUSB') {
            throw 'Device identity or service changed before restart. No restart attempted.'
        }
        Write-Output "Restarting only $($scopeBefore.InstanceId) using $scopePnpUtil."
        & $scopePnpUtil /restart-device $scopeBefore.InstanceId
        $scopeRestartExitCode = $LASTEXITCODE
        Write-Output "PnPUtil exit code: $scopeRestartExitCode"
        if ($scopeRestartExitCode -ne 0) { throw "Device restart did not report success (exit $scopeRestartExitCode). No different device or PC restart attempted." }
        $scopeAfterRestart = Wait-ScopeAfterRestart -ExpectedInstanceId $scopeBefore.InstanceId
        $scopeAfterRestart | Format-List
        Write-Output 'Verified exact scope service WinUSB and problem code zero after device restart.'
    }
    $scopeGuardAfter = Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard
    if (@($scopeGuardAfter.SecurityServicesRunning) -notcontains 2) { throw 'Memory integrity is not reported running after binding. Investigate before device use.' }
    Write-Output 'Memory integrity remains running. Driver binding completed; this does not validate scope protocol, capture accuracy, or machine safety.'
    if ($scopeResult.NeedReboot) { Write-Output 'Windows reports a reboot is required. The script has not rebooted the PC.' }
} catch {
    Write-Error -Message ("Binding did not fully complete: " + $_.Exception.Message + ". Review " + $scopeLog + ", " + $scopeBackupPath + ", and C:\Windows\INF\setupapi.dev.log. No automatic rollback or alternate driver attempt performed.") -ErrorAction Continue
    throw
} finally { Stop-Transcript | Out-Null }
