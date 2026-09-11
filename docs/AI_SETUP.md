# Set scope values from an AI task

The AI command line can read this DSO5102P's settings and configure supported
channel ranges, positions, timebase and Edge-trigger settings by name and value.
It reads the instrument after each individual panel gesture and stops if the
expected change is not confirmed. Hantek Studio 0.2 retains its relative panel
controls; this increment adds no desktop settings form, AI chat or provider API.

Use the configured Windows PC and the existing WinUSB connection. Read
[Operating guide](OPERATIONS.md) and [agent instructions](../AGENTS.md) first.
Pause automatic preview and disconnect the desktop app before an AI session.
Only one client may own the USB device; each `settings` or `configure` operation
keeps the same exclusive handle throughout its work.

## Workflow

Run these commands in 64-bit PowerShell 7. The first two are offline:

```powershell
& C:\Github\Hantek\scripts\scope.ps1 setup-capabilities
& C:\Github\Hantek\scripts\scope.ps1 validate-setup `
    -SettingsFile C:\Github\Hantek\examples\edge-ch1.json
```

After the authorized session's identity, echo and screen preflight, read current
settings into the requesting project's evidence folder:

```powershell
& C:\Github\Hantek\scripts\scope.ps1 settings `
    -LogDir C:\Github\MyProject\artifacts\scope-setup
```

Inspect `snapshot.state`, `unknown_fields` and `warnings`. Prepare a target file
containing only settings the task requires, then apply it:

```powershell
& C:\Github\Hantek\scripts\scope.ps1 configure `
    -SettingsFile C:\Github\MyProject\scope-setup.json `
    -LogDir C:\Github\MyProject\artifacts\scope-setup
& C:\Github\Hantek\scripts\scope.ps1 screenshot `
    -OutputDir C:\Github\MyProject\artifacts\scope
```

`configure` changes the scope. Offline validation checks the document and
supported values; device-dependent prerequisites are checked during the live
operation. A successful configuration has `status: "verified"` and
`settings_verified: true`. Its final settings must match every requested value.
A separate successful screenshot provides a visual record; configuration does
not silently capture, retry or restore anything.

The direct Python equivalents use `src/hantek_scope.py settings --log-dir ...`,
`configure --settings-file ... --log-dir ...`, `validate-setup --settings-file ...`
and `setup-capabilities`. The PowerShell launcher also accepts `-PythonPath` and
`-InterfaceGuid`; [runtime selection](OPERATIONS.md#runtime-and-configuration)
is unchanged. Use absolute paths when calling from another project.

## Target document and units

The file is UTF-8 JSON, at most 16 KiB, with exactly `schema_version` and
`settings`. Version 1 uses **flat dotted keys**, not nested channel objects.
Duplicate/unknown keys, booleans in numeric fields and non-finite numbers are
rejected before USB access. Use numbers in SI units, not strings such as `"1 V"`.

```json
{
  "schema_version": 1,
  "settings": {
    "ch1.volts_per_div": 1.0,
    "horizontal.seconds_per_div": 0.0008,
    "trigger.level_volts": 1.32
  }
}
```

[The complete CH1 Edge example](../examples/edge-ch1.json) also names coupling,
position, source, slope and mode. It expects a visible CH1, coarse scale, main
timebase and an existing usable Edge trigger. It preserves the selected probe
factor. Review an example against the real measurement before applying it.

| Setting | Accepted values and meaning |
| --- | --- |
| `ch1.probe`, `ch2.probe` | `1`, `10`, `100`, `1000`; instrument probe multiplier |
| `ch1.volts_per_div`, `ch2.volts_per_div` | Displayed V/div, including the selected probe multiplier |
| `ch1.position_div`, `ch2.position_div` | Vertical divisions, in exact 0.04-division increments |
| `ch1.coupling`, `ch2.coupling` | `dc`, `ac`, `gnd` |
| `horizontal.seconds_per_div` | An exact supported main-timebase value in seconds/div |
| `trigger.type` | `edge`; the instrument must already be in Edge mode |
| `trigger.source` | `ch1`, `ch2`, `ext`, `ext5`, `acline` |
| `trigger.mode` | `auto`, `normal` |
| `trigger.slope` | `rising`, `falling` |
| `trigger.coupling` | `dc`, `ac`, `noise-reject`, `hf-reject`, `lf-reject` |
| `trigger.level_volts` | Displayed Edge threshold in volts; enabled CH1/CH2 source required |

The supported base voltage ranges are 2, 5, 10, 20, 50, 100, 200 and 500 mV/div,
then 1, 2, 5 and 10 V/div. Multiply by the selected probe factor to obtain the
displayed scale. For example, base 0.1 V/div with a 10× multiplier is displayed
as 1 V/div. The 1 mV index is deliberately outside numeric setup support even
when it appears in raw readback. Fine adjustment is not decoded as a known
coarse range.

Timebase follows the instrument's 2/4/8 sequence by decade, from 4 ns/div to
40 s/div. Around 1 ms, the available values are **800 µs/div and 2 ms/div**;
1 ms/div is rejected. Use `setup-capabilities` for the exact machine-readable
list. Main timebase must be active, with matching main/window range indices.

The tool never silently rounds a requested position or trigger voltage to a
nearby knob step. Trigger voltage is quantized in source V/div divided by 25,
with the source's vertical position accounted for. At 1 V/div and position
−0.16 div, 1.32 V corresponds to raw trigger position 29. Level readback is
limited to central display coordinates: source and trigger positions must each
be within ±4 divisions. These are conservative software bounds, not a statement
of the instrument's full operating range.

The software probe multiplier must match the actual probe's attenuation switch
and connection. The agent cannot move or verify that switch. Changing the
software factor changes displayed volts; it does not change the physical probe.

## Preconditions and failure handling

Each `settings` or `configure` invocation reads only `/protocol.inf` and verifies
its exact SHA-256 before interpreting the 208-byte record. The supported profile
is `dso5102p-208-v1`, hash
`fbd58fa396f2e3922fcd8b9000ba505eb627ee162956937ce1a1f8b07169995d`.
Numeric setup also requires this tested USB descriptor's device-release BCD
`2430`, in addition to VID `049F` / PID `505A`. A matching schema hash alone
does not establish other models' range tables, units or behavior. This profile
does not claim general DSO5000-family compatibility.
An unknown profile, missing field, unsupported value or unreliable dependency
fails without guessing. Hidden channels are not enabled automatically. Trigger
type transitions are not part of numeric setup: use an ordinary, explicitly
observed front-panel action to establish Edge mode first.

Changing the active trigger source channel's scale, probe factor or position
also requires a reliable current threshold so its dependent changes can be
checked. This implies an existing Edge trigger, coarse source scale and valid
central coordinates. Adjusting a different enabled channel does not require an
unrelated trigger voltage. The engine also guards against acquisition changing
between stopped and active while configuration is in progress.

Changing the source range can quantize an unrequested trigger threshold. The
engine bounds that change at each step to one new display quantum; several
coarse-range steps can accumulate drift. It does not promise exact preservation
of every unrequested derived voltage. If a particular final threshold matters,
include `trigger.level_volts` in the target. That requested value must be exactly
representable and verified at the final scale; it is never silently rounded.

The engine has an 80-gesture and 120-second limit. It journals before each
gesture, sends one named control, checks its reply and matching echo, then reads
settings again. It checks expected progress and unrelated fields. Settling
intervals of 200 ms after schema/settings reads and the panel echo allow the
scope to leave its previous command handler.
It uses the existing bounded protocol implementation; no SYSData blob is written.

On failure, inspect `result.json`, the last readback and a fresh screen before
deciding what to do next. Partial changes may remain. There are no automatic
state-changing retries or rollback, and rerunning an unsuccessful setup is a
new decision. A screenshot checksum failure remains a failed capture even if
the configuration's independent settings readback succeeded.

Each run has a timestamped directory under `-LogDir`, containing `result.json`,
`journal.jsonl` and `operations/` with raw schema/settings, wire data and action
records. Keep the whole directory with the project's capture evidence. Raw
64-bit fields are preserved as Python integers; JSON consumers must not treat
large raw integers as exact JavaScript `Number` values. Named SI state is the
supported interpretation; raw fields alone are not a public setpoint interface.

`read-settings` still saves the raw record without interpreting it.
`read-protocol` is a read-only diagnostic for the single allowlisted schema
path; it accepts no arbitrary instrument path. Neither is a restorable preset.

## Validation boundary

The [AI setup session record](sessions/2026-09-12-ai-setup.md) distinguishes live
USB/display evidence from offline checks and remaining bench work. These tools
verify instrument settings, not probe wiring, calibration, measurement accuracy
or whether attached equipment is safe to operate. Raw waveform export, general
instrument file access, firmware, calibration, resets and DUT control remain
outside this increment.

The field layout and protocol references are the
[exact-model community project](https://github.com/titos-carrasco/DSO5102P-Python),
its [published schema](https://github.com/titos-carrasco/DSO5102P-Python/blob/181f290601c8eea43a00d8aa0add0d85ec8d19da/inf/protocol.inf),
the [related protocol implementation](https://github.com/uberdaff/dsoc-extended/blob/94fe96387420f620dfe5609bb18b1e99fc784d9c/dsoconn.py)
and [community menu IDs](https://www.mikrocontroller.net/articles/Hantek_Protokoll/Men%C3%BC-IDs).
The owner's actual schema and saved screens provide the model-specific checks.
Vendor schema files and private captures remain ignored local evidence.
