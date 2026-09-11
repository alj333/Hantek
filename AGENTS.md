# Working with the Hantek scope

## Purpose and scope

This repository is the reusable source of truth for the owner's Hantek DSO5102P
USB connection. Read `README.md`, `docs/OPERATIONS.md` and `docs/SETUP_WINDOWS.md`
before using hardware. Read `docs/PROTOCOL.md` before changing the client.

The tested hardware is one DSO5102P, USB VID `049F`, PID `505A`, on Windows 11
x64 using Microsoft's WinUSB. These IDs are not proof that a different model or
firmware behaves identically. Do not claim compatibility without evidence.

## Default workflow

- Default to offline tests and saved, clearly identified captures while editing.
- For an authorized live connection check, use `identify`, `echo`, then
  `screenshot`. Never rerun installation merely to take a capture.
- `acquisition-start` and `acquisition-stop` affect the **oscilloscope**, not the
  equipment being measured. Use them only within the user's authorized task.
  Observe the initial state, log actions and verify the resulting screen.
- Call the launcher by absolute path from another project and choose that
  project's output/log folder. Prefer one process at a time; the client opens the
  USB device exclusively.
- Normal commands run without elevation. Only the one-time driver-binding
  operation needs Windows administrator approval.
- Do not manipulate a Windows administrator/security approval dialog. Let the
  user approve it. If it is cancelled, stop that action and explain the result.

## Boundaries

- Keep Windows Memory Integrity and signature enforcement enabled. Do not add
  test certificates, use test-signing modes or weaken protection to load the old
  Hantek driver.
- The established path uses the Microsoft driver already in Windows. Never
  force a driver onto an unidentified device or relax the single-device check.
- Preserve the explicit command/payload allowlists, transfer deadlines, size and
  count limits, checksums, identity checks and exclusive device access.
- Do not add generic raw-command passthrough, scope shell access, instrument file
  writes, firmware updates, factory resets or automatic calibration.
- No signal generator, DUT control, CNC transfer/write/execution capability or
  network service is part of this repository. A future project needs its own
  explicit design and authorization for such capabilities.
- Physical probing and grounding are operator responsibilities. Follow the
  attached project's commissioning requirements before connecting production
  equipment. A successful scope command does not establish machine safety.

## Data and artifacts

- Save captures and operation logs under `artifacts/`, or an explicitly chosen
  project output directory. Save installation state under `.local/setup/`.
- `.local/archive/setup-2026-09-11/` is an immutable historical copy, not current
  source. Do not execute its legacy installers or use its old scripts as entry
  points. The working copies are under `src/` and `scripts/`.
- Do not put vendor executables, native drivers, manuals, local machine/USB
  instance identifiers, credentials, production measurements or personal paths
  into tracked source. Do not stage ignored files with `git add -f`.
- A capture's `.json`, `.wire.bin` and `.rgb565` files are supporting evidence.
  A failed or partial transfer must not be relabeled as successful.

## Definition of done

Run `python -m unittest discover -s tests -v` and
`pwsh -NoProfile -File .\tests\test_binding.ps1` for relevant changes. Add tests
for changed behavior and keep them offline. Check the launcher from a different
working directory when changing path/configuration behavior. Review the diff
and Git ignore coverage for local data and vendor artifacts.

Document capabilities and limitations accurately. Record meaningful live
validation in `docs/sessions/`, with local evidence paths and a clear distinction
between USB/screen verification and measurement accuracy. Update setup and
operating instructions when behavior changes. Do not rerun state-changing
hardware tests solely because files were moved or documentation changed.

## Desktop app and AI tools

The user app is `desktop/` (React and Electron); `src/desktop_bridge.py` reuses
the existing scope client. Keep both the desktop app and AI CLI functional.
Read `docs/DESKTOP_APP.md` before changing their integration.

- Preserve the renderer sandbox, context isolation, trusted main-frame IPC,
  fixed subprocess arguments, request validation, size/deadline bounds and
  single-operation guard. The app has no network service or AI-provider key.
- Demo mode must never open hardware or masquerade as a real measurement.
- Automatic preview is off on startup and stops on failure/disconnection. Its
  rolling scratch files are disposable; Save capture retains permanent evidence.
  Never apply preview cleanup to saved captures or the historical archive.
- The app's bundled Python and Electron runtimes are authorized build outputs,
  saved under ignored build/release directories. Do not add them to Git or
  include the archived vendor downloads in the package.
- For app changes run the Python suite, `npm test` and `npm run build` under
  `desktop/`, then appropriate demo UI checks (`npm run test:ui`). Packaged tests
  use `HANTEK_TEST_EXECUTABLE` to target the unpacked app executable.
- `desktop/tests/hardware-readonly.cjs --live` is an explicit live check, excluded
  from offline builds. It reads identity and screenshots only. Never enable live
  hardware checks in ordinary tests or substitute demo results for device proof.
