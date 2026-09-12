# ImageGen UI implementation — 12 September 2026

Delivered Hantek Studio 0.3.0 in the existing repository. The ImageGen reference,
prompt, asset provenance and representative demo screenshots are under
`docs/design/2026-09-12/`. See [design QA](../../design-qa.md) for the comparison
and checks, and [desktop instructions](../DESKTOP_APP.md) for operation/build steps.

## Changes

- Replaced the cream/green presentation with the selected graphite, amber and
  cyan design across Workspace, Controls, Captures and Settings.
- Added Workspace Refresh preview, Open controls and a recent saved-capture link.
- Grouped relative controls with channel colors and retained the full control
  catalog, softkeys, bounded steps and explicit uncertain-request state.
- Added offline Inter font and its redistribution license. The generated concept
  remains documentation, while displayed screens come from the existing client.
- Added layout/interaction regression checks and neutral empty-catalog status.
- Preserved the separate AI CLI and existing USB/security/integrity boundaries.

## Validation and package

98 Python, 41 backend and 47 packaged UI checks passed (186 total). TypeScript,
Vite, frozen bridge self-test and the Windows portable build also passed. Demo
tests used isolated profiles, including minimum-window and exact reference-size
screenshots. No new scope command or live hardware test was performed.

Portable app: `desktop/release/Hantek-Studio-0.3.0-Windows.exe` (107,700,448 bytes).
SHA-256: `EC816539F1B3CD7A8F1905B40042D0EF1319867D0A115A4D3497ED42F5290A53`.
Build log: `.local/build/redesign-package.log`. Runtime/executable artifacts stay
ignored by Git. The font license is included at `resources/licenses/Inter-LICENSE.txt`.

The previous 0.2 window was already disconnected and displayed a checksum failure
after an earlier panel request. The redesign did not retry that request or infer
its result. Version 0.3 was opened using the same user profile, with both saved
captures retained, hardware disconnected and automatic refresh off. Historical
screen images remain labelled as previous/saved evidence.

## Relay

Use `scripts/start-desktop.ps1` to open the current packaged version. Continue
hardware commissioning with the existing control checklist and AI setup guide;
this visual increment does not change their validation status. For later UI
changes, run the checks in the desktop guide, inspect demo screenshots and update
`design-qa.md`. Keep the generated concept separate from real scope evidence.
