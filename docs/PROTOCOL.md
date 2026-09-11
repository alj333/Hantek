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

All other commands/payloads are rejected. In particular, panel-lock values of
`0x12` are excluded. `identify` only reads USB metadata. The source retains an
offline `decode` command that never opens USB.

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
- [Microsoft WinUSB API usage](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/using-winusb-api-to-communicate-with-a-usb-device)

Related-model implementations are evidence about protocol possibilities, not
proof of compatibility with this exact model. Retain attribution for any future
code copied from external projects and comply with its actual license. This
repository does not grant rights to Hantek software, manuals or other third-party
material.
