# Using the scope from a project

Use this repository as a shared tool. Keep project-specific measurements and
analysis in the project that requested them. The scope connection remains local
USB; nothing needs to be exposed on a network.

## Agent handoff

Give another project's agent this instruction, adapting the output path:

> Use the Hantek tools in `C:\Github\Hantek`. Read that repository's `AGENTS.md`
> and operating/setup notes. The existing USB connection uses WinUSB; do not
> reinstall drivers. Start with identification and a screen capture, saving
> artifacts in this project's `artifacts\scope` directory. Change acquisition
> state only when this task calls for it. Report actual evidence and limitations.

Before probing a device, establish the signal type, voltage, reference/ground,
probe attenuation and bandwidth requirements with the operator. This repository
does not automate physical probe connection or determine whether a machine can
safely be measured.

## Normal session

1. Confirm the scope is powered and connected to its configured PC USB port.
2. Run `identify` to check identity/endpoints. If that fails, diagnose the
   connection; do not start with a driver reinstall.
3. Use `echo` for a basic round-trip check, then `screenshot` to read the display.
4. Inspect the screen and record relevant channel, range, timebase and probe
   settings. Pixel capture alone does not establish trustworthy numeric data.
5. If authorized to freeze acquisition, capture the initial state, run
   `acquisition-stop`, then take another screenshot. Resume with
   `acquisition-start` when required and verify the resulting indicator.

Never assume an acknowledgement proves execution. The command logs deliberately
separate the received reply from verification of the instrument's displayed
state. An interrupted command is an unknown result; inspect before retrying.

## Outputs

A successful screenshot produces files sharing a timestamped name:

| File | Purpose |
| --- | --- |
| `.png` | Decoded screen for viewing |
| `.rgb565` | Full original screen-pixel payload |
| `.wire.bin` | Received protocol bytes, including recorded status replies |
| `.json` | Identity, timestamp, requested command, decoding, checksums and result |

The JSON status must be `complete`, with the expected image size and checksums,
before treating a capture as successful. An exception can still leave useful
partial files; preserve their failure status. Capture filenames include
subsecond timestamps to avoid collisions.

The `.rgb565` file is screen data, **not waveform ADC samples**. The client cannot
yet calculate calibrated frequency, RMS or pulse timing from raw waveforms.
Reading a value visibly displayed by the scope is a different operation and
should be described as such.

To decode saved screen pixels without accessing hardware:

```powershell
python C:\Github\Hantek\src\hantek_scope.py decode capture.rgb565 decoded.png
```

Choose a new output filename; decoding refuses to overwrite an existing file.

Acquisition actions write separate JSON command logs. Keep these with the
project's captures so state changes can be explained later. Measurements and
device-instance information should remain in the chosen project's approved
storage; review them before sharing or adding them to Git.

## Runtime and configuration

- `scripts/scope.ps1 -Help` shows launcher options without touching hardware.
- `-PythonPath` or `HANTEK_PYTHON` selects a trusted interpreter explicitly.
- `-InterfaceGuid` / Python `--guid` selects an explicitly configured interface.
- Otherwise `HANTEK_INTERFACE_GUID` takes precedence over the dedicated default.
- `-OutputDir` and `-LogDir` direct artifacts to another project.
- Direct Python invocation exposes equivalent `--output-dir` / `--log-dir`
  arguments on the relevant subcommands.

The default artifact paths are relative to the repository, independent of the
calling directory. Explicit relative paths are relative to the caller's current
directory. Use absolute paths for unambiguous cross-project work.

## Current limitations

Only the five established live device commands are supported. The
[desktop app](DESKTOP_APP.md) adds periodic screen previews and a capture
library around them. There is no generic panel control, raw waveform acquisition, firmware management,
scope filesystem access, shell access or remote network endpoint. Add future
capabilities as individually bounded operations, with offline protocol tests
and a specific live validation procedure.
