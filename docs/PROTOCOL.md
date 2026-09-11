# Protocol and implementation notes

This is an independently implemented client based on original community
protocol work and observed behavior of the owner's DSO5102P. It is not an
official Hantek SDK. No vendor executable was decompiled or loaded by the client.
The original Python implementations were reference material, not bundled runtime
dependencies.

## Transport

The tested device presents VID `049F`, PID `505A`, interface 0 / alternate 0,
with bulk OUT `0x02` and bulk IN `0x81`, each with a 512-byte maximum packet size.
The client uses Windows `setupapi`, `kernel32` and `winusb` through Python ctypes.
It opens one matching interface exclusively, then verifies the USB descriptor
and endpoints before sending protocol requests.

The normal packet layout is:

```text
0x53 | uint16 little-endian body length | command | payload | checksum
```

Body length includes command, payload and checksum. The checksum is the low
eight bits of the sum of all preceding packet bytes. USB transfers may split
frames or return multiple frames together, so the reader buffers and validates
protocol frames independently of transfer boundaries.

## Allowed operations

| Operation | Request | Payload | Expected reply |
| --- | --- | --- | --- |
| Echo | `0x00` | Bounded unique bytes | `0x80` with identical bytes |
| Screenshot | `0x20` | Empty | `0xA0` chunks and completion |
| Start scope acquisition | `0x12` | `00 00` | Known short `0x92` replies |
| Stop scope acquisition | `0x12` | `00 01` | Known short `0x92` replies |
| Read settings record | `0x01` | Empty | Bounded raw `0x81` reply |
| Read profile description | `0x10` | Exact allowlisted `/protocol.inf` request | `0x90` chunks and checksum completion |
| Named panel gesture | `0x13` | Allowlisted key ID, `01` | `0x93`; interpretation is documented below |

All other commands/payloads are rejected. In particular, panel-lock values of
`0x12` are excluded. `identify` only reads USB metadata. `controls` returns the
shared control catalog offline, and `decode` never opens USB.
`setup-capabilities` and `validate-setup` are also offline. The file request is
not a general file API: callers cannot supply another path or write a file.

## Ordinary front-panel control

`src/control_catalog.json` is the single mapping used by Python and the desktop.
It contains only named ordinary panel gestures. Inputs never accept arbitrary
key numbers, payload bytes, debug headers or a command sequence.

Each `0x13` request uses one key and `01`. Rotary counts are implemented as 1–5
separate exchanges, with a shared transaction deadline and progress recorded
after each step. Buttons accept one press. There are no state-changing retries.
The source implementation in dsoc-extended reports that an additional command
is needed to process a buffered key; the client follows each accepted key reply
with a unique normal-protocol echo and requires its matching response. A 200 ms
settling interval follows the key acknowledgement before sending that echo;
the transaction deadline is checked again after the interval. On this scope,
the immediate echo after the first key timed out even though the screen changed.
Subsequent tested exchanges with the interval completed successfully. The timed
out exchange remains recorded as failed; the client never ignores a missing echo.

The published protocol describes the one-byte `0x93` payload as the menu ID
**before** the key action. It is not a boolean success code or readback of the
requested setting. Preserve the payload and timing; do not claim execution from
it. See the controls session record for this unit's actual response shape.
Context-dependent soft keys must be chosen from the current displayed ordinary
menu. A reply obtained after sending a soft key cannot preflight that same key.

`0x01` returns a firmware-specific settings blob. Preserve it and its wire bytes
with size/checksum validation; do not apply related-model offsets or scale tables
as if they were validated on this DSO5102P. The numeric AI workflow below uses a
separately validated fixed profile. There is no SYSData settings write, preset
restore or raw waveform transfer here.

## Fixed-profile AI setup

`src/scope_settings.py` decodes the exact 208-byte, 119-field profile identified
by schema SHA-256
`fbd58fa396f2e3922fcd8b9000ba505eb627ee162956937ce1a1f8b07169995d`.
Each live `settings` or `configure` invocation fetches `/protocol.inf` on the
same exclusive handle and checks this hash before interpreting settings.
Numeric setup additionally requires the tested device-release descriptor BCD
`2430` with VID `049F` / PID `505A`. The schema hash is not proof that another
model has the same units, range tables or semantics.
The schema transfer requires valid framing and bulk checksum, bounded size and
completion, and no trailing data. A 200 ms settling interval follows this bulk
response before the next request. No vendor schema asset is shipped in Git.
The setup adapter also waits 200 ms after each settings read and panel echo
before issuing its next operation; this pacing avoids the observed next-command
timeout while preserving all reply checks and deadlines.

All raw fields are retained. Only supported enumerations and SI values appear
in named state; unsupported or unreliable fields are omitted with warnings.
Displayed channel scale includes the probe factor. Coarse voltage ranges,
2/4/8 timebase steps, positions and Edge threshold mapping are documented in
[AI setup](AI_SETUP.md), with exact-unit evidence in
[the session record](sessions/2026-09-12-ai-setup.md).

`src/scope_setup.py` converges only through named single panel gestures. It
validates a target, reads current settings, journals the next gesture, waits
for the normal panel/echo exchange, and reads settings again. Each step must
show expected progress without disallowed unrelated changes. The transaction
is bounded to 80 gestures and 120 seconds. It never writes the full SYSData blob,
resends a failed gesture, rolls back implicitly or reports success from `0x93`.
Requested final settings are compared with fresh readback; this is instrument
configuration verification, not measurement calibration. Hantek Studio 0.2's
relative control interface remains unchanged.

## Screenshot rules

An `0xA0` payload beginning with `01` carries screen pixels. A payload `02 xx`
terminates the image and supplies its whole-image checksum. Require exactly
768000 bytes (800 × 480 × 2), valid frame and bulk checksums, and no unexpected
trailing data. Decode as little-endian RGB565. This interpretation produced
legible, correctly colored displays on the tested scope.

The device was observed emitting these additional valid short frames:

```text
53 03 00 92 00 E8
53 04 00 92 01 00 EA
```

During screenshots, only those exact payload forms are tolerated as asynchronous
status replies, with a count limit of eight and the full packets logged. An
image-bearing `0x92`, another command, a malformed frame or a checksum failure
still fails. Never broaden this into silently skipping arbitrary responses.

Acquisition commands collect bounded known short acknowledgements until a
three-second USB idle timeout. Neither idle nor an acknowledgement establishes
execution; compare screenshots for the actual displayed state.

## Failure behavior

Per-transfer timeouts, a transaction deadline, maximum frame/data counts and
exclusive access prevent unbounded reads and overlapping clients. Raw data and
metadata are retained when screenshot processing fails. There are no automatic
state-changing retries. Closing a connection during an outstanding screenshot
can leave an incomplete transfer; recovery must be deliberate and read-only,
with a deadline and retained evidence.

## Source references

- [Exact-model DSO5102P Python project](https://github.com/titos-carrasco/DSO5102P-Python)
- [Original DSO5102P implementation](https://github.com/titos-carrasco/DSO5102P-Python/blob/master/rcr/dso5102p/DSO5102P.py)
- [DSO5000P screenshot example](https://gist.github.com/jsjolund/69fe7eef3a59c139fc9546fbbf20889a)
- [Related dsoc-extended implementation](https://github.com/uberdaff/dsoc-extended/blob/master/dsoconn.py)
- [Original protocol discussion](https://www.mikrocontroller.net/articles/Diskussion:Hantek_Protokoll)
- [Community protocol and key mapping](https://www.mikrocontroller.net/articles/Hantek_Protokoll)
- [Documented menu IDs](https://www.mikrocontroller.net/articles/Hantek_Protokoll/Men%C3%BC-IDs)
- [Microsoft WinUSB API usage](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/using-winusb-api-to-communicate-with-a-usb-device)

Related-model implementations are evidence about protocol possibilities, not
proof of compatibility with this exact model. Retain attribution for any future
code copied from external projects and comply with its actual license. This
repository does not grant rights to Hantek software, manuals or other third-party
material.
