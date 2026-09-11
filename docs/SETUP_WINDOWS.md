# Windows setup and recovery

## Existing configured PC

The owner's scope is already bound to Microsoft WinUSB and has passed live USB,
screen-capture and acquisition-control tests. **Do not run installation again to
use it.** Use the same physical PC USB port and start with `identify`.

Windows can still show `Gadget Serial v2.4` as the device name. The decisive
checks are USB VID `049F`, PID `505A`, service `WINUSB` and problem code zero.
The descriptive name alone is not an error.

The established interface GUID is:

```text
{5cb35641-beea-4a98-b06b-3cf4dca1911b}
```

This is a reusable interface identifier, not a secret or a USB serial number.
An existing valid GUID is preserved during binding. If another valid GUID is
already registered, use that value in `-InterfaceGuid`, `--guid`, or
`HANTEK_INTERFACE_GUID` when operating the client.

## Requirements

- Windows x64; live validation used Windows 11 Pro.
- PowerShell 7 x64 for the scripts. The original Windows PowerShell 5 launch was
  blocked by its existing script policy. We did not weaken that policy.
- A trusted Python 3.8+ runtime; Python 3.12 x64 was used for validation. The client
  has no third-party package dependencies.
- A powered DSO5102P and a USB data cable from the rear USB-B device port to the
  PC. Initial testing should use disconnected probe inputs.

## One-time binding on a new connection

Run the read-only preflight first from the repository:

```powershell
pwsh -NoProfile -File .\scripts\bind-winusb.ps1
```

It must identify exactly one matching present device and the existing Microsoft
`winusb.inf`, section `WINUSB`. Zero or multiple devices, an unexpected driver or
a mismatched identity are reasons to stop and inspect the connection.

Only when a new binding is actually needed, run the same helper from an
administrator PowerShell 7 terminal after the user approves Windows elevation:

```powershell
.\scripts\bind-winusb.ps1 -Apply -RestartDevice
```

The helper selects Microsoft's existing driver, backs up the previous binding
and interface values, registers the interface GUID if needed, and optionally
restarts only the identified USB device. It does not reboot the PC, change scope
firmware or alter Windows security settings. It requires Memory Integrity to
remain running. Local setup records are written beneath `.local/setup/` by
default; use `-StateDirectory` for a deliberate alternative.

After binding, verify `WINUSB` and problem zero, then run:

```powershell
.\scripts\scope.ps1 identify
.\scripts\scope.ps1 echo
.\scripts\scope.ps1 screenshot
```

Inspect the image against the scope's display. This verifies the connection and
screen decoding; it does not calibrate the scope or validate waveform units.

## Known driver issue

The official Hantek driver package selected Cypress/Hantek version 3.4.7.0. Its
digital signatures were valid, but Windows blocked `dstusbAMD64.SYS` because it
was incompatible with hypervisor enforcement. Device Manager reported problem
39; Code Integrity event 3111 recorded status `0xC0000220` and failure bitmap
`0x2`.

Microsoft WinUSB resolved the connection while Memory Integrity stayed enabled.
The Hantek desktop application was never installed. That application expects its
vendor driver; this repository's WinUSB client is the supported path here.

## Recovery

- **No interface found:** confirm power/cable/port, inspect the device identity
  and registered GUID. A different physical port may create a new device instance.
- **Device busy:** close other scope clients. Do not remove exclusive access to
  let two agents issue commands simultaneously.
- **Driver warning:** inspect the actual selected driver and Windows error. Do
  not turn off security protection or substitute a driver from another model.
- **Administrator prompt cancelled:** the requested change was not authorized;
  obtain the user's instruction to retry before opening another prompt.
- **Failure during binding:** read the saved log and backup before retrying.
  Driver binding may have succeeded even if the device briefly disappeared
  during restart. Check current state before applying changes again.
- **Rollback:** use only the saved device-specific prior binding/interface
  values. Restoring the old Hantek driver restores its incompatibility too; it
  does not make that driver safe to load. Do not delete unrelated driver packages.
- **Interrupted capture:** retain the failed artifacts. Do not interpret partial
  data or automatically retry a state-changing command. A pending transfer may
  need a bounded read-only cleanup before a new request.
- **Echo reports unexpected reply `92`:** pending acquisition-status messages
  can remain between sessions. Echo deliberately requires its exact response;
  do not weaken that check or reinstall a driver. Preserve the failure and use
  deliberate bounded reads to reach USB idle before retrying an observational
  request. See the repository handoff session for the observed recovery.

## Primary references

- [Microsoft WinUSB installation](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/winusb-installation)
- [SetupDiOpenDeviceInfo and inherited driver lists](https://learn.microsoft.com/en-us/windows/win32/api/setupapi/nf-setupapi-setupdiopendeviceinfow)
- [Selecting an installed driver](https://learn.microsoft.com/en-us/windows/win32/api/setupapi/nf-setupapi-setupdisetselecteddriverw)
- [DiInstallDevice](https://learn.microsoft.com/en-us/windows/win32/api/newdev/nf-newdev-diinstalldevice)
- [Official DSO5000P driver listing](https://www.hantek.com/download?key=fwsc&pid=26&sid=3&word=dso5102p)
