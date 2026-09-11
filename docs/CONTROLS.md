# Instrument controls

Hantek Studio 0.2 provides 39 named gestures for the DSO5102P's ordinary front
panel, alongside the existing explicit Run and Stop actions. Both the Windows
app and AI CLI use the same catalog and USB implementation. This supports
setting changes through the scope's menus while retaining the real scope screen
as the reference for values and menu context.

## Desktop use

Connect, then open **Controls**. The left side shows the scope screen and the
right side groups its controls. Use **Refresh preview** when the image is old.
Each control sends one request and attempts a new preview. Automatic preview
stops before a control request; another operation cannot overlap it.

| Control group | Use |
| --- | --- |
| Channel 1 / Channel 2 | Open the channel menu; adjust V/div and vertical position; press position to request zero |
| Horizontal | Adjust time/div and horizontal position; open horizontal/window controls |
| Trigger | Open the trigger menu; move/press the level knob; set to 50%; force a trigger |
| Acquisition | Autoset and Single; Run and Stop remain available separately |
| Menus | Measure, Acquire, Cursor, Display, Math/FFT |
| Soft keys | F1–F5 act on the displayed menu; Select left/right/press operates the multifunction knob |

Channel coupling, probe factor, bandwidth and inversion are reached through
the channel menus. Trigger type/source/slope/mode/coupling are reached through
the trigger menu. Acquisition modes, measurements, cursor choices and FFT
options are reached through their respective menus. Availability and soft-key
meaning depend on the current scope screen and firmware; the app does not
guess the selected menu item or run a blind series of menu presses.

Choose 1–5 steps for a rotary control. Ordinary buttons always send one press.
There is no press-and-hold repeat. CH1/CH2 buttons can toggle channel visibility
when their menu is already active; check the current screen before pressing.
Autoset can change several settings. Single and Force trigger affect acquisition.

The app reports a **request**, followed by a screen. It does not turn a USB
acknowledgement into a verified setting. A checksum-verified image establishes
that its pixels transferred correctly; it does not establish measurement accuracy.
Validation badges describe the tests recorded for this particular scope, not
automatic verification of the current request.

**Save settings record** obtains the raw settings response and saves it under
operation logs. This is diagnostic evidence for firmware validation. It is not
a restorable preset or a calibrated numeric settings display.

Demo mode never opens USB. Knob gestures alter a synthetic waveform and the
image records the last simulated gesture. Menu actions are interaction rehearsals,
not a complete emulation of Hantek firmware. Demo images retain their DEMO label.

## AI command line

For actual channel ranges, timebase or Edge-trigger values, use the separate
[AI setup guide](AI_SETUP.md). The commands below remain the direct relative
gesture interface used by the desktop.

List the exact supported IDs without touching hardware:

```powershell
& C:\Github\Hantek\scripts\scope.ps1 controls
```

After the authorized session's identity/echo/screenshot preflight, request a
single gesture and inspect a new screenshot:

```powershell
& C:\Github\Hantek\scripts\scope.ps1 panel-control -Control ch1-scale-plus -Count 1
& C:\Github\Hantek\scripts\scope.ps1 screenshot

& C:\Github\Hantek\scripts\scope.ps1 panel-control -Control trigger-menu
& C:\Github\Hantek\scripts\scope.ps1 screenshot
```

Inspect the displayed ordinary menu before choosing a soft key or Select action:

```powershell
& C:\Github\Hantek\scripts\scope.ps1 panel-control -Control softkey-2
& C:\Github\Hantek\scripts\scope.ps1 screenshot
```

The Python equivalents are:

```powershell
python C:\Github\Hantek\src\hantek_scope.py controls
python C:\Github\Hantek\src\hantek_scope.py panel-control timebase-minus --count 1 --log-dir .\artifacts\scope-logs
python C:\Github\Hantek\src\hantek_scope.py read-settings --log-dir .\artifacts\scope-logs
```

The CLI intentionally leaves screenshot capture as a separate step so an agent
can choose its evidence destination. The desktop obtains that screenshot itself.
Pause the desktop preview and disconnect before an AI session takes over.

## Records and failures

Panel logs are created before the first state-changing write. They distinguish
attempted, sent, acknowledged and completed gesture counts. Completed means the
protocol exchange finished, not that the scope executed the intended setting.
Every rotary step uses the same bounded exchange. A failure stops the remaining
steps; it never retries a setting change. Inspect the log and screen before any
further request because even a failed transfer may have changed the scope.

If the command finishes but its following desktop preview fails, the app reports
an unverified result and disconnects. It does not resend the command. A fresh,
deliberate read-only capture can establish the displayed state. Keep failed
evidence; never bypass packet or image checksum validation.

## Deliberate limits

The desktop controls remain relative. Profile-checked numeric settings and
bounded named-value configuration are available through the [AI CLI](AI_SETUP.md),
with firmware validation and fresh readback after each gesture. General settings
restoration, raw waveform export and computed signal analysis remain separate
future work. Use the scope's measurement/FFT menus for their displayed results.

Utility, Save/Recall, Save to USB, Default Setup, Probe Check and undocumented
F0/F6/F7 functions are absent. Firmware, factory reset, calibration, instrument
filesystem writes, shell/debug access and panel locking remain outside this app.
Do not operate those menus with the context-dependent soft keys or Select knob.

See [Protocol notes](PROTOCOL.md) for command evidence and
[Bench checklist](CONTROLS_CHECKLIST.md) for remaining hands-on work.
