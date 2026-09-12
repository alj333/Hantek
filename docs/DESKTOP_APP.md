# Hantek Studio desktop app

Hantek Studio is a local Windows app for the owner's Hantek DSO5102P. It provides
a screen workspace, saved-capture library, explicit acquisition Run/Stop and
39 ordinary front-panel controls. The app uses the same bounded USB client as the repository's AI tools.
It does not contain an AI chat or require an API key.

The Windows package includes Electron and Python. **Using the built app does not
require installing Python, Node.js or the Hantek desktop software.** A new PC
still needs the one-time Microsoft WinUSB binding described in
[Windows setup](SETUP_WINDOWS.md). The app does not install or change drivers.

This guide describes version 0.3.0. The redesign uses dark graphite surfaces,
amber primary actions, cyan accents, thin outline icons and a bundled Inter
variable font across Workspace, Controls, Captures and Settings. Font loading
works offline and does not install a font into Windows. See the
[ImageGen prompt](design/2026-09-12/prompt.md),
[selected concept image](design/2026-09-12/workspace-concept.png) and
[asset provenance and license](design/2026-09-12/assets.md) for the design reference.
The concept is a mockup; actual scope pixels, capture metadata and connection
state remain the sources for the implemented interface.

See the [control guide](CONTROLS.md),
[bench checklist](CONTROLS_CHECKLIST.md), [controls validation record](sessions/2026-09-11-controls.md)
and original [desktop validation record](sessions/2026-09-11-desktop.md) for completed checks
and any outstanding validation; the original CLI's live results do not by
themselves establish that the packaged desktop app has been tested on hardware.

## Open the app

After a successful build, double-click:

```text
C:\Github\Hantek\desktop\release\Hantek-Studio-0.3.0-Windows.exe
```

This portable package runs without installing an application. The repository
also provides a launcher from PowerShell 7 x64:

```powershell
& C:\Github\Hantek\scripts\start-desktop.ps1
```

Add `-Demo` to that launcher to open with simulated signals selected. This saves
Demo as the current mode; switch back in Settings when connecting real USB.

The alternative is `desktop/release/win-unpacked/Hantek Studio.exe`. Keep the
**entire `win-unpacked` folder** together; its resources contain the bundled
scope client and runtime. Do not copy only that executable.

The app allows one active instance. Opening it again brings the existing app
forward. Closing during a scope operation waits for it to finish. Normal use
does not need administrator rights.

## First session

1. Open Settings and choose USB instrument or Demo workspace. Demo is useful for
   learning the interface without a connected scope; its images are always
   labelled as simulated.
2. For USB, power the scope and connect its rear USB-B port to the configured PC
   USB port. Select Connect. The app checks the USB identity before enabling
   connected operations.
3. Use the connection check for an echo test, then **Refresh preview** in the
   workspace toolbar to capture the screen. Inspect
   the displayed acquisition indicator and the channel, probe and timebase
   settings shown by the instrument.
4. Save a capture when you need a lasting record. In the library, add a title
   and notes, export a PNG, or reveal the original files.

The app remembers preferences and saved captures, but it starts disconnected.
Changing the mode, interface GUID, refresh interval or storage directory ends
the current app connection; reconnect after saving preferences. Changing the
storage directory leaves previous captures in their original directory.

## Find your way around

The left navigation keeps four views available:

| View | Main actions |
| --- | --- |
| Workspace | Connect, refresh or save the screen, request Run/Stop, inspect session details and recent activity |
| Controls | Operate the existing named front-panel gestures alongside the scope screen |
| Captures | Select saved images, edit titles/notes, export PNG and reveal files |
| Settings | Choose USB or Demo, storage location, interface GUID and refresh interval |

The workspace's **Open controls** button opens Controls directly. **Capture
library** opens Captures; clicking **Recent capture** opens the actual newest
saved capture and selects its library entry. When there are no saved captures,
the card explains how to create one. A temporary preview is not shown as a
saved record. Session details use the current connection and capture metadata.

The captured instrument screen stays fully contained with every edge visible.
Demo mode remains clearly labelled throughout these views.

## Screen preview and acquisition controls

Live preview requests successive **screenshots**. It is not a waveform stream,
and the refresh interval is not the scope's sampling rate. Settings accepts
intervals from 3 to 60 seconds; the default is 5 seconds. Each transfer finishes
before another scope operation starts.

Use the toolbar's **Refresh preview** icon for one deliberate screen request.
**Auto-refresh** enables successive requests at the selected interval and starts
off. It stops when you leave Workspace, change settings, disconnect or encounter
an error. **Save capture** creates a new lasting library record.

Preview frames are temporary. Use a saved capture for measurements or records
you want to keep. Successful preview cleanup retains the newest three preview
directories; temporary preview evidence can be removed by later previews.

Run and Stop change the oscilloscope's acquisition only. Before using either,
inspect the current screen. The app logs the explicit request, then requests a
fresh preview. A reply or a finished USB transfer does not prove execution:
**check the instrument's displayed acquisition indicator**. The app does not
automatically infer Run/Stop state from its pixels.

If a state request or its following screen refresh fails, the result remains
unverified. Read the message and inspect the scope before deciding what to do.
There is no automatic retry of the state-changing request. Disconnecting or
closing the app leaves the scope's acquisition state unchanged.

## Files and preferences

The **Controls** view adds channels, horizontal/timebase, trigger, acquisition,
measurement, display, cursor, math and soft-key gestures alongside a fresh scope
screen. Rotary controls allow 1–5 steps per click; buttons allow one press.
The [control guide](CONTROLS.md) explains menus, interpretation and AI commands.
Control requests stop automatic preview and are never retried automatically.
The app does not infer numeric settings from the pixels or acknowledge a value
as applied without a human/agent inspecting the displayed result.

When launched from this repository's build/launcher arrangement, local files
use these directories:

| Location | Contents |
| --- | --- |
| `.local/desktop-profile/` | App preferences and temporary preview data |
| `artifacts/captures/` | Saved hardware screenshots and original transfer evidence |
| `artifacts/logs/` | Acquisition/panel-request logs and raw settings records |
| `artifacts/demo/logs/` | Clearly labelled simulated control requests |
| `artifacts/demo/captures/` | Clearly identified generated demo images and metadata |

When the package is moved outside the repository, it uses the Windows user's
application-data location for its profile and a Hantek Studio directory under
Documents for capture storage. Use Settings to select another local storage
directory. The chosen directory is a **storage root**: the app adds `captures`,
`logs`, and `demo/captures` beneath it.

A saved hardware screen includes `.png`, `.json`, `.rgb565` and `.wire.bin`
files with the same timestamped stem. The latter three retain identity,
timestamps, protocol evidence and checksum results. The original transfer
metadata is preserved when you edit a capture's title or notes; annotations
are written separately as `.notes.json`. Titles allow 120 characters and notes
allow 8000 characters.

The library shows up to the newest 100 valid saved captures across hardware and
demo sources. Failed or incomplete transfers remain files on disk and are not
shown as successful captures. Exporting a PNG exports the image, not the full
set of transfer evidence or notes. Copy the supporting files when an audit or
another project needs them. Review measurements and device identifiers before
sharing files.

The normal interface GUID is
`5cb35641-beea-4a98-b06b-3cf4dca1911b`. Change it only to match the GUID actually
registered for the device. This identifies a Windows device interface; it is
not the scope's serial number.

## Use alongside an AI agent

The existing `scripts/scope.ps1` launcher and `src/hantek_scope.py` CLI remain
available. An agent can identify, echo, capture, list controls, save a settings
record and request authorized acquisition or panel changes without driving the
desktop interface. The separate [AI setup workflow](AI_SETUP.md) reads supported
numeric settings and applies a checked JSON target with fresh readback after
each gesture. These named-value commands remain available through the CLI;
the redesigned desktop controls continue to send relative panel gestures. See the
[operating guide](OPERATIONS.md) for cross-project commands and output paths.

The desktop app opens USB only for an individual operation, so the CLI can use
the scope between app operations. **Turn off automatic preview and wait for any
active transfer to finish before the agent operates.** Disconnecting or closing
the app provides a clear handoff. Do not run two scope operations concurrently;
the client deliberately opens the device exclusively.

Python is bundled for the app's internal adapter. The existing standalone CLI
launcher still follows its documented Python-runtime selection. The package
does not add SSH, a network service, an AI provider or an API-key setting.

## Build and offline checks

The build toolchain uses Windows x64, PowerShell 7 x64, Node.js 24 and Python
3.12 x64. Build dependencies require downloading on the first build. End users
of the completed package do not need these development tools.

From the repository, run:

```powershell
pwsh -NoProfile -File .\scripts\build-desktop.ps1
```

Use `-PythonPath C:\Path\To\python.exe` or `HANTEK_PYTHON` when an explicit build
interpreter is needed. The script accepts Python 3.12 or later, 64-bit; the
recorded toolchain uses 3.12. `-SkipInstall` reuses dependencies already installed
in this checkout; it does not skip compilation or checks. Use the normal build
after changing either dependency lock or build requirements.

The build script installs the locked npm dependencies, creates a local Python
build environment, packages the adapter with PyInstaller, runs the React build
and offline checks, and produces the Windows portable app. Build environments,
dependencies and output packages are local build products, not source files.

The Python bundle uses PyInstaller's directory layout and includes the standard
library used by the scope client. Electron launches that private executable
with its console streams redirected and its console window hidden. The bundle
does not use a machine-wide Python installation.

These focused checks do not access USB:

```powershell
python -m unittest discover -s tests -v
python .\src\desktop_bridge.py --self-test
Set-Location .\desktop
npm test
npm run test:ui
npm run test:controls
npm run test:preview-failures
npm run test:redesign
npm run build
```

Use a trusted Python executable explicitly if `python` resolves to a Windows
Store alias. `--self-test` reports the adapter protocol version, runtime,
architecture, allowed actions and limits; it does not enumerate or open USB.
The build must also run this check against the frozen adapter before a package
is treated as usable. See the session record for package and UI test results.

For source UI work, run `npm run build` followed by `npm start` from `desktop/`.
The Electron host loads the built local assets. Development uses
`HANTEK_PYTHON`, the repository build environment, or a discovered trusted Python;
the packaged app always uses its bundled runtime. For isolated demo checks, set
absolute `HANTEK_STUDIO_PROFILE` and `HANTEK_STUDIO_DATA_DIR` directories, then
run `npm start -- --demo`. Use both overrides to keep test preferences and
generated captures separate from the regular profile and storage root.

## Developer boundary

The React renderer uses the narrow API in `desktop/shared/contracts.ts`.
Electron owns native dialogs, selected storage directories, known capture-file
lookup and process creation. The service serializes operations and keeps demo
mode separate from hardware. The renderer cannot supply an arbitrary executable,
shell command or raw scope command.

The window uses context isolation and sandboxing with Node integration disabled.
Its host serves bundled assets through the local `hantek://app/` scheme, refuses
renderer navigation/new windows and permission requests, and blocks HTTP(S) and
WebSocket requests. IPC accepts the app's main frame and the listed operations.
Keep these boundaries intact when extending the interface.

`src/desktop_bridge.py` accepts exactly one UTF-8 JSON object on stdin, at most
16384 bytes. The caller must close stdin after writing. The only actions are
`identify`, `echo`, `screenshot`, `acquisition-start`, `acquisition-stop`,
`controls` (offline), `panel-control`, and `read-settings`.
An optional `guid` follows the CLI's interface configuration. A screenshot
requires an absolute local `output_dir`; acquisition, panel-control and
read-settings require an absolute local `log_dir`. Panel-control additionally
requires a catalog `control` ID and accepts an integer `count` (default 1).
Unrelated keys, unknown keys, invalid
configuration and unsupported actions fail before device access.

The adapter writes exactly one JSON response line. A handled request exits zero;
the caller must inspect `ok`, not just the process exit code:

```json
{"ok":true,"result":{"echo":"ok","instrument_settings_changed":false}}
```

```json
{"ok":false,"error":"USB transfer failed","result":{"status":"incomplete"}}
```

`result` is the existing client's metadata, including retained failure evidence
when available. It is omitted on errors that produced no metadata. This example
is illustrative, not a live record. Preserve the original client allowlists,
checksums, transfer limits and failure semantics. Do not add automatic recovery
or broaden the desktop bridge into a raw-command or filesystem interface.

## Limits and troubleshooting

- Voltage range, timebase and trigger adjustment are available as named panel
  gestures. The desktop does not add absolute setpoint inputs or numeric setup
  readback; use the separate [AI CLI](AI_SETUP.md) for its supported profile-checked
  values. Calibrated measurement readback, raw waveform extraction and signal
  analysis are not implemented. The screen's RGB565 data is displayed pixels,
  not ADC samples.
- Demo images never represent a measurement from the connected instrument.
- The connection has been established for one DSO5102P; other models and
  firmware are unverified.
- For a missing device, check power, cable, configured PC port and interface
  GUID. Do not reinstall the driver merely because a capture failed.
- For an unavailable/busy device, stop automatic preview and close competing
  clients before reconnecting.
- A checksum failure means the new screen was rejected. The app retains its
  failed evidence and labels any older image as historical. One such failure
  occurred during validation; do not disable integrity checks to accept a frame.
  Reconnect to request another screen after the operation has ended. Preserve
  useful diagnostics outside the disposable preview folder before further work.
- For pending status packets, failed transfers or a driver warning, follow
  [Windows recovery notes](SETUP_WINDOWS.md#recovery). Keep Windows Memory
  Integrity and driver-signature enforcement enabled.
- The app cannot move a physical probe switch or configure grounding, a DUT, signal generators or
  production machinery. A successful capture does not validate measurement
  accuracy or establish safe physical connections.

## Implementation references

The 0.3 redesign passed 186 offline/demo checks. See the
[release record](sessions/2026-09-12-ui-redesign.md) and
[visual QA report](../design-qa.md) for results and screenshot comparisons.

- [Electron security guidance](https://www.electronjs.org/docs/latest/tutorial/security)
- [Electron process sandboxing](https://www.electronjs.org/docs/latest/tutorial/sandbox)
- [PyInstaller packaging and bundled runtimes](https://www.pyinstaller.org/en/stable/operating-mode.html)
- [Windows packaging options](https://www.electron.build/v26/docs/win/)
