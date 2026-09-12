# Hantek DSO5102P control

Local Windows tools for an AI agent or a person to inspect and control a
USB-connected Hantek DSO5102P. The scope performs signal acquisition; this
repository handles communication, screenshots and ordinary front-panel control.

## Desktop app

**Hantek Studio** is the standalone Windows React desktop app in `desktop/`.
Open `desktop/release/Hantek-Studio-0.3.0-Windows.exe` after building, or run
`scripts/start-desktop.ps1`. Its Python runtime is included in the package.

The app provides a scope screen workspace with automatic preview, explicit
Run/Stop, 39 named front-panel controls, a saved-capture library with titles and
notes, PNG export, connection settings and a clearly labelled demo mode. Read the
[desktop user and build guide](docs/DESKTOP_APP.md) for details.

Version 0.3.0 gives Workspace, Controls, Captures and Settings a consistent dark
graphite interface with amber actions, cyan accents and bundled offline Inter
typography. The workspace has a direct Refresh preview action, an Open controls
shortcut and a recent saved capture that opens its library entry. Its visual
reference is preserved with the [ImageGen prompt](docs/design/2026-09-12/prompt.md),
[concept image](docs/design/2026-09-12/workspace-concept.png) and
[asset sources and license](docs/design/2026-09-12/assets.md).

The AI tools below remain available alongside the app. Pause automatic preview
and disconnect the app before an agent takes over the USB connection.

## What works

Verified on the owner's DSO5102P with Windows 11 x64 on 11 September 2026:

| Command | Result |
| --- | --- |
| `identify` | Read USB identity and endpoint descriptors |
| `echo` | Verify a unique request/response token |
| `screenshot` | Retrieve and decode the 800 × 480 scope screen |
| `acquisition-stop` | Stop the oscilloscope's acquisition |
| `acquisition-start` | Resume the oscilloscope's acquisition |

Stop and resume were verified against the displayed acquisition indicators.
The scope was left acquiring in Auto mode after the test.

Desktop controls include channel scale/position, timebase, trigger controls,
ordinary menus and their soft keys. These are **relative panel gestures**, with a fresh
screen after each desktop action. See the [control guide](docs/CONTROLS.md)
and [validation checklist](docs/CONTROLS_CHECKLIST.md) for what has been checked
and what still needs the physical bench.

The AI CLI additionally provides profile-checked numeric `settings` and
`configure` from a JSON target file. It can select supported channel ranges,
positions, timebase and Edge-trigger values, checking fresh instrument readback
after each gesture. See [AI setup by named values](docs/AI_SETUP.md) for accepted
values, prerequisites and evidence. The desktop 0.3 controls remain relative.

Raw waveform extraction and signal analysis are not implemented. A screenshot
contains displayed pixels, not original waveform samples. Other Hantek models
and firmware versions have not been validated.

## Quick start on the configured PC

Keep the powered scope connected through its **rear USB-B port** to the same PC
USB port used during setup. Run from **PowerShell 7, 64-bit**:

```powershell
Set-Location C:\Github\Hantek
.\scripts\scope.ps1 -Help
.\scripts\scope.ps1 identify
.\scripts\scope.ps1 echo
.\scripts\scope.ps1 screenshot
.\scripts\scope.ps1 controls
.\scripts\scope.ps1 setup-capabilities
```

The launcher finds a usable Python 3.8+ runtime; it accepts `-PythonPath` or
`HANTEK_PYTHON` when an explicit runtime is needed. The client uses only Python's
standard library. Python 3.12 x64 was used for the live validation.

New screenshots and their supporting records go to `artifacts/captures/`.
Acquisition, panel-control and settings commands write records to `artifacts/logs/`. Both are
ignored by Git. Normal operation needs no administrator rights, Hantek desktop
application, Pi, SSH connection or network service.

On a new PC or after changing ports, follow [Windows setup](docs/SETUP_WINDOWS.md)
before attempting communication. Do not reinstall a driver on every run.

## Use from another project

Call this repository's launcher by absolute path and choose that project's
capture folder:

```powershell
& C:\Github\Hantek\scripts\scope.ps1 screenshot `
    -OutputDir C:\Github\MyProject\artifacts\scope

& C:\Github\Hantek\scripts\scope.ps1 acquisition-stop `
    -LogDir C:\Github\MyProject\artifacts\scope-commands
```

Use acquisition commands only when that project has authorized changing the
scope's acquisition state. Confirm the initial and resulting states on screen.
The project should ignore its measurement artifacts in Git, unless a reviewed
fixture is deliberately being added.

The direct Python interface is also available:

```powershell
python C:\Github\Hantek\src\hantek_scope.py identify
python C:\Github\Hantek\src\hantek_scope.py screenshot --output-dir .\artifacts\scope
```

Device-interface selection supports `--guid`, `HANTEK_INTERFACE_GUID`, or the
documented default GUID. An explicit launcher override uses `-InterfaceGuid`.
The client still requires exactly one matching device and verifies the USB
descriptor before sending a scope command.

## Repository guide

- [AGENTS.md](AGENTS.md): instructions for agents working on or using these tools.
- [Desktop app](docs/DESKTOP_APP.md): launch, capture library, build and packaging.
- [Windows setup](docs/SETUP_WINDOWS.md): driver binding, administrator approval,
  port changes and recovery.
- [Operating guide](docs/OPERATIONS.md): captures, state changes and integration.
- [Protocol notes](docs/PROTOCOL.md): known commands, framing and limitations.
- [Instrument controls](docs/CONTROLS.md): desktop controls and AI command examples.
- [AI setup](docs/AI_SETUP.md): read named values and apply a checked settings file.
- [Bench checklist](docs/CONTROLS_CHECKLIST.md): remaining hands-on validation.
- [Initial validation record](docs/sessions/2026-09-11.md): evidence and lessons
  from the first connection.
- `src/`: scope client; `scripts/`: launch and driver-setup helpers; `tests/`:
  offline checks.

## Preserved work

The entire original Downloads setup was copied into
`.local/archive/setup-2026-09-11/`, including vendor downloads, the original
scripts, raw captures, failed-transfer evidence, command logs and driver backups.
That archive is local-only and ignored by Git. The working source in `src/` and
`scripts/` is now authoritative; the archive remains a historical snapshot.
All 59 original files were verified against the archive; the SHA-256 manifest
is `.local/migration-manifest-2026-09-11.json`.

The original Downloads folder was retained. Vendor installers, drivers and
manuals are not redistributed by this repository. Source links are recorded in
the documentation. Preserve the ignored archive separately if backing up or
moving the whole local project; a Git clone will contain only the tracked tools,
tests and documentation.

## Development checks

These checks do not access USB hardware:

```powershell
python -m unittest discover -s tests -v
pwsh -NoProfile -File .\tests\test_binding.ps1
```

Use a trusted Python executable explicitly if `python` is a Windows Store alias.
Do not substitute a live acquisition test for an offline test. For a requested
hardware check, begin with `identify`, then `echo`, then a screenshot.
