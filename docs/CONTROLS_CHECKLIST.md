# Controls bench validation

Use this checklist at the physical scope on 12 September 2026. The user authorized
remote development on the preceding evening and deferred checks requiring
hands-on access. No task or reminder is scheduled by this document.

The built app exposes source-backed panel gestures. **Available** means implemented;
**screen-verified** means a specific displayed effect was observed on this unit.
Neither means every range, firmware variant or measurement has been validated.
The detailed remote evidence is in [the controls session](sessions/2026-09-11-controls.md).

Remote single-step screen checks passed for CH1 V/div ±, time/div ±, trigger
level ±, CH1 menu, Trigger menu and F1 in the CH1 coupling menu (9 catalog entries).
The other 30 entries remain pending. The checks below still cover range limits,
signal behavior and physical-screen agreement even for those nine entries.

## Preparation

- [ ] Use the owner's DSO5102P and the configured Windows USB connection.
- [ ] Launch the new version; confirm USB mode, automatic preview off, one client.
- [ ] Save a baseline screen and settings record; note channel visibility,
  coupling, probe factor, V/div, time/div, position, trigger type/source/level,
  acquisition state and current menu.
- [ ] Connect an appropriate known test signal with the operator's probe and
  ground checks. Record its expected amplitude/frequency and probe attenuation.
- [ ] Compare the app's displayed screen with the physical screen.

## Test sequence

For each item, send one gesture, inspect both screens, save evidence, and record
the before/after value. Do not infer an absolute setting from a step count. Use
the explicit opposite step to restore only after observing what changed.

| Group | Required physical checks |
| --- | --- |
| CH1 | V/div ± at several ranges; position ± and zero; menu/visibility behavior; coupling, probe factor, bandwidth and inversion through the menu |
| CH2 | Enable and compare to CH1 using the same known signal; V/div ±, position ±/zero and channel menu options |
| Horizontal | Time/div ± at fast/slow ranges; position direction and zero; window/zoom options |
| Trigger | Level ± and knob press; 50% on a known waveform; source/type/slope/mode/coupling choices |
| Acquisition | Existing Run/Stop; Single waits/captures as expected; Force trigger; Autoset changes documented settings |
| Measure | Select displayed measurements and compare them with the known signal |
| Acquire | Normal, Peak Detect and averaging choices; compare displayed behavior |
| Cursor | Select source/type; move both cursors with multifunction controls and confirm readouts |
| Display | Confirm selected rendering/grid/persistence options shown by this firmware |
| Math/FFT | Select operation/source and verify against suitable input signals |
| Soft keys | F1–F5 focus/activation behavior in each ordinary menu; Select left/right/press on known choices |
| Repeat count | 2 and 5 rotary steps send exactly that many gestures; boundaries saturate as the physical knob does |
| App recovery | Disconnect/reconnect at idle; unplug only at an agreed test point; unknown results remain unverified and are not resent |
| AI handoff | Disconnect the desktop, use the CLI for one gesture/capture/settings record, then reconnect the desktop |

Utility, calibration, reset, firmware and instrument save menus are outside this
checklist. Do not enter them through physical controls while using contextual
soft keys or the multifunction controls remotely.

## Record each result

Copy this row into the session record for each tested control:

| Control ID / count | Starting menu and value | Observed result | Restored state | Log and before/after capture paths | Pass / fail / pending |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

For a failure, preserve the JSON and wire bytes, stop automatic preview and
inspect the physical state. A sent request can have taken effect even when its
reply or next image failed. Do not retry a setting change automatically.

## Completion

- [ ] Restore the agreed baseline and save a final screen/settings record.
- [ ] Review logs for partial or unknown gestures.
- [ ] Update catalog validation badges only for observed gestures; link evidence
  in the session note. Leave untested variants pending.
- [ ] Keep measurement evidence under ignored `artifacts/` or the chosen project
  folder. Do not add real device identifiers or captures to Git.
- [ ] Rebuild the desktop if the catalog or implementation changes.

Numeric settings decoding, absolute setpoints, preset restoration and waveform
export are future implementation work, not features to mark passed from a
front-panel gesture test.
