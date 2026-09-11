"""Small DSO5102P WinUSB client. Python standard library; no external packages.

Identify reads USB descriptors. Echo and screenshot leave acquisition unchanged.
Explicit acquisition and named ordinary panel commands change only this scope.
Raw settings readback makes no assumptions about field layout or units.
These operations are unrelated to CNC machine operation. No panel locks,
instrument filesystem access, shell/debug commands, resets, firmware operations,
or driver installation are implemented.

Protocol evidence (not vendor-authorized API documentation):
https://github.com/titos-carrasco/DSO5102P-Python/blob/master/rcr/dso5102p/DSO5102P.py
https://gist.github.com/jsjolund/69fe7eef3a59c139fc9546fbbf20889a
https://github.com/uberdaff/dsoc-extended/blob/master/dsoconn.py
WinUSB: https://learn.microsoft.com/windows-hardware/drivers/usbcon/using-winusb-api-to-communicate-with-a-usb-device

The 800x480 RGB565 little-endian decoder is a protocol-source-based assumption
until a capture is compared with this particular instrument's display. Raw pixel
data and packet bytes are preserved so no evidence is lost during decoding.
"""

import argparse
import ctypes as C
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import struct
import sys
import time
import uuid
import zlib

import scope_controls

VID, PID = 0x049F, 0x505A
WIDTH, HEIGHT = 800, 480
MAX_IMAGE_BYTES = WIDTH * HEIGHT * 2
MAX_WIRE_BYTES = MAX_IMAGE_BYTES + 256 * 1024
MAX_FRAMES = 4096
TIMEOUT_MS = 3000
TRANSACTION_SECONDS = 30
# Short replies observed on this unit (00, 0100), plus the documented echoed
# acquisition payloads (0000, 0001). These never stand in for image data.
KNOWN_ACQUISITION_ACKS = frozenset((b"\x00", b"\x01\x00", b"\x00\x00", b"\x00\x01"))
OBSERVED_ASYNC_ACKS = frozenset((b"\x00", b"\x01\x00"))
MAX_ASYNC_ACKS = 8
MAX_SETTINGS_BYTES = 65533  # One maximum-length frame minus command/checksum.
MAX_CONTROL_WIRE_BYTES = 65536
PANEL_SETTLE_SECONDS = 0.2
DEFAULT_INTERFACE_GUID = "5cb35641-beea-4a98-b06b-3cf4dca1911b"
REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CAPTURE_DIR = REPOSITORY_ROOT / "artifacts" / "captures"
DEFAULT_LOG_DIR = REPOSITORY_ROOT / "artifacts" / "logs"


class ScopeError(Exception):
    pass


def configured_interface_guid(explicit=None, environ=None):
    """An explicit GUID overrides the environment, then the dedicated default."""
    environment = os.environ if environ is None else environ
    value = explicit if explicit is not None else environment.get(
        "HANTEK_INTERFACE_GUID", DEFAULT_INTERFACE_GUID)
    try:
        return str(uuid.UUID(value.strip()))
    except (ValueError, AttributeError) as error:
        raise ValueError("Invalid interface GUID; use --guid or HANTEK_INTERFACE_GUID with a valid GUID") from error


def output_directory(value):
    """Explicit relative paths belong to the calling project, not this repo."""
    return Path(value).expanduser().resolve()


def request_packet(command, payload=b""):
    """Allow observational requests and the two explicit acquisition actions."""
    if command not in (0x00, 0x01, 0x12, 0x13, 0x20):
        raise ScopeError("Command is outside the scope allowlist")
    if command == 0x12 and payload not in (b"\x00\x00", b"\x00\x01"):
        raise ScopeError("Only scope acquisition start/stop payloads are allowed")
    if command == 0x13 and not scope_controls.allowed_payload(payload):
        raise ScopeError("Only catalogued ordinary panel keys with a single press are allowed")
    if (command in (0x01, 0x20) and payload) or len(payload) > 256:
        raise ScopeError("Invalid request payload")
    packet = b"\x53" + struct.pack("<H", len(payload) + 2)
    packet += bytes((command,)) + bytes(payload)
    return packet + bytes((sum(packet) & 255,))


class FrameReader:
    """USB reads may split protocol frames or return several in one read."""
    def __init__(self, read, deadline, wire_sink=None, *, max_wire_bytes=MAX_WIRE_BYTES,
                 max_frames=MAX_FRAMES):
        self.read = read
        self.deadline = deadline
        self.buffer = bytearray()
        self.total = 0
        self.frames = 0
        self.wire_sink = wire_sink
        self.last_frame = None
        self.async_ack_packets = []
        self.max_wire_bytes = max_wire_bytes
        self.max_frames = max_frames

    def _fill(self, count):
        while len(self.buffer) < count:
            if time.monotonic() >= self.deadline:
                raise ScopeError("Transaction exceeded its 30-second deadline")
            block = self.read()
            if not block:
                raise ScopeError("USB returned an empty transfer before completion")
            self.total += len(block)
            if self.total > self.max_wire_bytes:
                raise ScopeError("Response exceeded the bounded transfer size")
            if self.wire_sink:
                self.wire_sink.write(block)
            self.buffer.extend(block)

    def _next_frame(self):
        self.frames += 1
        if self.frames > self.max_frames:
            raise ScopeError("Too many response frames")
        self._fill(3)
        if self.buffer[0] != 0x53:
            raise ScopeError("Unexpected response marker: %02x" % self.buffer[0])
        body_length = int.from_bytes(self.buffer[1:3], "little")
        if not 2 <= body_length <= 65535:
            raise ScopeError("Invalid frame length")
        frame_length = body_length + 3
        self._fill(frame_length)
        frame = bytes(self.buffer[:frame_length])
        del self.buffer[:frame_length]
        if sum(frame[:-1]) & 255 != frame[-1]:
            raise ScopeError("Response frame checksum mismatch")
        self.last_frame = frame
        return frame[3], frame[4:-1]

    def next(self, response_command, allow_observed_async_ack=False):
        while True:
            command, payload = self._next_frame()
            if command == response_command:
                return payload
            if (allow_observed_async_ack and command == 0x92
                    and payload in OBSERVED_ASYNC_ACKS):
                # This instrument emitted these exact short status replies before
                # screenshot data after acquisition-stop. Preserve each; never
                # reinterpret an image-bearing 0x92 reply as an 0xA0 image frame.
                self.async_ack_packets.append(self.last_frame.hex())
                if len(self.async_ack_packets) > MAX_ASYNC_ACKS:
                    raise ScopeError("Too many asynchronous acquisition status replies")
                continue
            raise ScopeError("Unexpected response command: %02x" % command)


def acquisition_acknowledgements(reader, records):
    """Consume known short replies until a bounded USB idle timeout.

    This unit produced 0100 then 00 for one request. There is no established
    terminal marker, so a 3-second idle interval closes the receive operation.
    Idle is not proof of execution. Never resend a state-changing request here.
    """
    while len(records) < MAX_ASYNC_ACKS:
        try:
            payload = reader.next(0x92)
        except OSError as error:
            if (getattr(error, "winerror", None) == 121 or error.errno == 121):
                if records and not reader.buffer:
                    return
            raise
        records.append({"received_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "packet_hex": reader.last_frame.hex(), "payload_hex": payload.hex()})
        if payload not in KNOWN_ACQUISITION_ACKS:
            raise ScopeError("Unrecognized acquisition acknowledgement payload; physical state unknown")
    raise ScopeError("Acquisition acknowledgement count exceeded its bound")


def screenshot_pixels(reader, raw_sink):
    pixels = bytearray()
    while True:
        payload = reader.next(0xA0, allow_observed_async_ack=True)
        if not payload:
            raise ScopeError("Screenshot response has no subtype")
        if payload[0] == 1:
            data = payload[1:]
            if not data or len(pixels) + len(data) > MAX_IMAGE_BYTES:
                raise ScopeError("Screenshot chunk empty or image too large")
            raw_sink.write(data)
            pixels.extend(data)
        elif payload[0] == 2:
            if len(payload) != 2:
                raise ScopeError("Unrecognized screenshot completion payload")
            if (sum(pixels) & 255) != payload[1]:
                raise ScopeError("Screenshot bulk checksum mismatch")
            if len(pixels) != MAX_IMAGE_BYTES:
                raise ScopeError("Expected 768000 RGB565 bytes; got %d" % len(pixels))
            if reader.buffer:
                raise ScopeError("Unexpected trailing response data")
            return bytes(pixels)
        else:
            raise ScopeError("Unrecognized screenshot subtype: %02x" % payload[0])


def rgb565_png(pixels, width=WIDTH, height=HEIGHT, byte_order="little"):
    if len(pixels) != width * height * 2:
        raise ScopeError("Raw image size does not match RGB565 dimensions")
    if byte_order not in ("little", "big"):
        raise ScopeError("Invalid pixel byte order")
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # PNG filter: none
        for x in range(width):
            i = (y * width + x) * 2
            word = int.from_bytes(pixels[i:i + 2], byte_order)
            r, g, b = (word >> 11) & 31, (word >> 5) & 63, word & 31
            rows.extend(((r << 3) | (r >> 2), (g << 2) | (g >> 4),
                         (b << 3) | (b >> 2)))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
            + chunk(b"IEND", b""))


U8, U16, U32 = C.c_ubyte, C.c_uint16, C.c_uint32
BOOL, HANDLE, PTR = C.c_int32, C.c_void_p, C.c_void_p
INVALID_HANDLE = C.c_void_p(-1).value


class GUID(C.Structure):
    _fields_ = [("Data1", U32), ("Data2", U16), ("Data3", U16),
                ("Data4", U8 * 8)]


class InterfaceData(C.Structure):
    _fields_ = [("cbSize", U32), ("InterfaceClassGuid", GUID),
                ("Flags", U32), ("Reserved", C.c_size_t)]


class DeviceInfo(C.Structure):
    _fields_ = [("cbSize", U32), ("ClassGuid", GUID), ("DevInst", U32),
                ("Reserved", C.c_size_t)]


class UsbInterface(C.Structure):
    _pack_ = 1
    _fields_ = [(name, U8) for name in (
        "bLength", "bDescriptorType", "bInterfaceNumber", "bAlternateSetting",
        "bNumEndpoints", "bInterfaceClass", "bInterfaceSubClass",
        "bInterfaceProtocol", "iInterface")]


class PipeInfo(C.Structure):
    _fields_ = [("PipeType", C.c_int32), ("PipeId", U8),
                ("MaximumPacketSize", U16), ("Interval", U8)]


def bind(dll, name, restype, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = restype, args
    return fn


def check(ok, label):
    if not ok:
        code = C.get_last_error()
        raise OSError(code, label + ": " + C.FormatError(code))


class WinUsbScope:
    def __init__(self, interface_guid):
        if os.name != "nt":
            raise ScopeError("Live USB access requires Windows")
        self.file_handle, self.usb_handle = None, HANDLE()
        self.guid = str(uuid.UUID(interface_guid.strip("{}")))
        self.setup = C.WinDLL("setupapi", use_last_error=True)
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.usb = C.WinDLL("winusb", use_last_error=True)
        self._bind()
        try:
            device = self._find_one()
            self.path = device["device_path"]
            self.metadata = device
            self.file_handle = self.CreateFileW(self.path, 0xC0000000, 0,
                                                None, 3, 0x40000000, None)
            if self.file_handle == INVALID_HANDLE:
                self.file_handle = None
                check(False, "Cannot open the scope; close other scope programs")
            check(self.Initialize(self.file_handle, C.byref(self.usb_handle)),
                  "WinUSB initialize")
            self._inspect()
        except BaseException:
            self.close()
            raise

    def _bind(self):
        self.GetClassDevs = bind(self.setup, "SetupDiGetClassDevsW", HANDLE,
                                 PTR, C.c_wchar_p, HANDLE, U32)
        self.EnumInterfaces = bind(self.setup, "SetupDiEnumDeviceInterfaces", BOOL,
                                   HANDLE, PTR, PTR, U32, PTR)
        self.GetDetail = bind(self.setup, "SetupDiGetDeviceInterfaceDetailW", BOOL,
                              HANDLE, PTR, PTR, U32, PTR, PTR)
        self.GetProperty = bind(self.setup, "SetupDiGetDeviceRegistryPropertyW", BOOL,
                                HANDLE, PTR, U32, PTR, PTR, U32, PTR)
        self.GetInstance = bind(self.setup, "SetupDiGetDeviceInstanceIdW", BOOL,
                                HANDLE, PTR, C.c_wchar_p, U32, PTR)
        self.DestroySet = bind(self.setup, "SetupDiDestroyDeviceInfoList", BOOL, HANDLE)
        self.CreateFileW = bind(self.kernel, "CreateFileW", HANDLE, C.c_wchar_p,
                                U32, U32, PTR, U32, U32, HANDLE)
        self.CloseHandle = bind(self.kernel, "CloseHandle", BOOL, HANDLE)
        self.Initialize = bind(self.usb, "WinUsb_Initialize", BOOL, HANDLE, PTR)
        self.Free = bind(self.usb, "WinUsb_Free", BOOL, HANDLE)
        self.GetDescriptor = bind(self.usb, "WinUsb_GetDescriptor", BOOL,
                                  HANDLE, U8, U8, U16, PTR, U32, PTR)
        self.QueryInterface = bind(self.usb, "WinUsb_QueryInterfaceSettings", BOOL,
                                   HANDLE, U8, PTR)
        self.QueryPipe = bind(self.usb, "WinUsb_QueryPipe", BOOL, HANDLE, U8, U8, PTR)
        self.SetPolicy = bind(self.usb, "WinUsb_SetPipePolicy", BOOL,
                              HANDLE, U8, U32, U32, PTR)
        self.ReadPipe = bind(self.usb, "WinUsb_ReadPipe", BOOL,
                             HANDLE, U8, PTR, U32, PTR, PTR)
        self.WritePipe = bind(self.usb, "WinUsb_WritePipe", BOOL,
                              HANDLE, U8, PTR, U32, PTR, PTR)

    def _find_one(self):
        guid = GUID.from_buffer_copy(uuid.UUID(self.guid).bytes_le)
        devset = self.GetClassDevs(C.byref(guid), None, None, 0x12)
        if devset == INVALID_HANDLE:
            check(False, "Enumerate USB interfaces")
        matches = []
        try:
            for index in range(1024):
                info = InterfaceData()
                info.cbSize = C.sizeof(info)
                if not self.EnumInterfaces(devset, None, C.byref(guid), index,
                                           C.byref(info)):
                    if C.get_last_error() == 259:
                        break
                    check(False, "Enumerate interface")
                needed = U32()
                devinfo = DeviceInfo()
                devinfo.cbSize = C.sizeof(devinfo)
                ok = self.GetDetail(devset, C.byref(info), None, 0,
                                    C.byref(needed), C.byref(devinfo))
                if ok or C.get_last_error() != 122:
                    raise ScopeError("Unexpected interface detail size response")
                if not 8 <= needed.value <= 65536:
                    raise ScopeError("Unexpected interface detail size")
                detail = C.create_string_buffer(needed.value)
                C.cast(detail, C.POINTER(U32))[0] = 8 if C.sizeof(PTR) == 8 else 6
                check(self.GetDetail(devset, C.byref(info), detail, needed.value,
                                     None, C.byref(devinfo)), "Read interface details")
                path = C.wstring_at(C.addressof(detail) + 4)
                ids_buffer = C.create_string_buffer(8192)
                ids_size, ids_type = U32(), U32()
                check(self.GetProperty(devset, C.byref(devinfo), 1,
                                       C.byref(ids_type), ids_buffer, len(ids_buffer),
                                       C.byref(ids_size)), "Read hardware IDs")
                if ids_type.value != 7 or ids_size.value > len(ids_buffer):
                    raise ScopeError("Invalid hardware ID property")
                hardware_ids = ids_buffer.raw[:ids_size.value].decode("utf-16-le").strip("\0").split("\0")
                if not any(re.fullmatch(r"USB\\VID_049F&PID_505A(?:&REV_[0-9A-F]{4})?",
                                        item.upper()) for item in hardware_ids):
                    continue
                instance = C.create_unicode_buffer(1024)
                check(self.GetInstance(devset, C.byref(devinfo), instance,
                                       len(instance), None), "Read device instance ID")
                matches.append({"device_path": path, "hardware_ids": hardware_ids,
                                "instance_id": instance.value,
                                "interface_guid": self.guid})
            else:
                raise ScopeError("Interface enumeration limit exceeded")
        finally:
            self.DestroySet(devset)
        if len(matches) != 1:
            raise ScopeError("Expected exactly one present VID049F PID505A interface; found %d" % len(matches))
        return matches[0]

    def _inspect(self):
        descriptor = C.create_string_buffer(18)
        count = U32()
        check(self.GetDescriptor(self.usb_handle, 1, 0, 0, descriptor, 18,
                                 C.byref(count)), "Read USB device descriptor")
        if count.value != 18 or descriptor.raw[:2] != b"\x12\x01":
            raise ScopeError("Unexpected USB device descriptor")
        vendor, product, version = struct.unpack_from("<HHH", descriptor.raw, 8)
        if (vendor, product) != (VID, PID):
            raise ScopeError("USB descriptor does not match VID049F PID505A")
        interface = UsbInterface()
        check(self.QueryInterface(self.usb_handle, 0, C.byref(interface)),
              "Read interface descriptor")
        if interface.bInterfaceNumber != 0 or interface.bAlternateSetting != 0:
            raise ScopeError("Expected interface 0, alternate setting 0")
        pipes = []
        for i in range(interface.bNumEndpoints):
            pipe = PipeInfo()
            check(self.QueryPipe(self.usb_handle, 0, i, C.byref(pipe)), "Query USB pipe")
            pipes.append({"address": pipe.PipeId, "type": pipe.PipeType,
                          "max_packet_size": pipe.MaximumPacketSize})
        for required in (0x02, 0x81):
            if sum(p["address"] == required and p["type"] == 2 for p in pipes) != 1:
                raise ScopeError("Expected bulk endpoint %02X not found" % required)
            # This is a host transfer deadline, not an instrument setting change.
            timeout = U32(TIMEOUT_MS)
            check(self.SetPolicy(self.usb_handle, required, 3, C.sizeof(timeout),
                                 C.byref(timeout)), "Set bounded USB timeout")
        self.metadata.update(vid="%04X" % vendor, pid="%04X" % product,
                             device_version_bcd="%04X" % version,
                             descriptor_hex=descriptor.raw.hex(), endpoints=pipes,
                             interface_number=interface.bInterfaceNumber,
                             timeout_ms=TIMEOUT_MS)

    def send(self, command, payload=b""):
        packet = request_packet(command, payload)
        buffer = C.create_string_buffer(packet)
        count = U32()
        check(self.WritePipe(self.usb_handle, 0x02, buffer, len(packet),
                             C.byref(count), None), "Send allowed scope request")
        if count.value != len(packet):
            raise ScopeError("USB write was incomplete")

    def read(self):
        buffer = C.create_string_buffer(65536)
        count = U32()
        check(self.ReadPipe(self.usb_handle, 0x81, buffer, len(buffer),
                            C.byref(count), None), "Read scope reply")
        return buffer.raw[:count.value]

    def close(self):
        if self.usb_handle.value:
            self.Free(self.usb_handle)
            self.usb_handle = HANDLE()
        if self.file_handle is not None:
            self.CloseHandle(self.file_handle)
            self.file_handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _write_operation_record(path, metadata, mode="w"):
    with path.open(mode, encoding="utf-8") as log:
        json.dump(metadata, log, indent=2)


def _check_transaction_deadline(deadline):
    if time.monotonic() >= deadline:
        raise ScopeError("Transaction exceeded its 30-second deadline; no further gesture sent")


def panel_control(device, control_id, count, log_dir):
    """Send only explicitly requested gestures, preserving each progress stage.

    Normal 0x93 contains a pre-action menu ID, not proof of execution. A single
    observational echo follows each acknowledged key because the related-model
    implementation reports that its arrival processes a buffered gesture. No
    gesture or echo is retried, and neither is interpreted as a state readback.
    """
    control = scope_controls.control_spec(control_id, count)
    payload = bytes((control["keycode"], 1))
    packet = request_packet(0x13, payload)
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    log_path = log_dir / ("panel-control-" + stamp + ".json")
    wire_path = log_dir / ("panel-control-" + stamp + ".wire.bin")
    metadata = {"requested_at_utc": stamp, "command": "panel-control",
                "control": control_id, "label": control["label"], "count": count,
                "device": device.metadata, "validation": control["validation"],
                "context_dependent": control["context_dependent"],
                "status": "prepared", "instrument_state_verified": False,
                "send_attempted_count": 0, "sent_count": 0,
                "acknowledged_count": 0, "completed_count": 0,
                "gesture_records": [], "log_path": str(log_path.resolve()),
                "wire_path": str(wire_path.resolve()),
                "ack_semantics": "0x93 is the pre-action menu ID. Echo checks communication after the key; neither verifies execution. Inspect the resulting screen."}
    _write_operation_record(log_path, metadata, "x")
    reader = None
    try:
        with wire_path.open("xb") as wire:
            deadline = time.monotonic() + TRANSACTION_SECONDS
            reader = FrameReader(device.read, deadline, wire,
                                 max_wire_bytes=MAX_CONTROL_WIRE_BYTES, max_frames=32)
            for index in range(count):
                _check_transaction_deadline(deadline)
                gesture = {"index": index + 1, "request_hex": packet.hex(),
                           "status": "send_attempted_result_unknown"}
                metadata["gesture_records"].append(gesture)
                metadata["send_attempted_count"] += 1
                metadata["status"] = "send_attempted_result_unknown"
                # This record closes before each potentially state-changing send.
                _write_operation_record(log_path, metadata)
                device.send(0x13, payload)
                metadata["sent_count"] += 1
                gesture["status"] = "awaiting_acknowledgement"
                _write_operation_record(log_path, metadata)
                answer = reader.next(0x93, allow_observed_async_ack=True)
                gesture["ack_packet_hex"] = reader.last_frame.hex()
                gesture["ack_payload_hex"] = answer.hex()
                if len(answer) != 1:
                    raise ScopeError("Panel acknowledgement must contain exactly one pre-action menu ID")
                gesture["menu_id_before_action"] = answer[0]
                metadata["acknowledged_count"] += 1
                gesture["status"] = "acknowledged_execution_unverified"
                _write_operation_record(log_path, metadata)
                # The first live key changed the screen but an immediate echo
                # timed out. Allow the panel handler to settle before the one
                # observational follow-up; this never resends the gesture.
                time.sleep(PANEL_SETTLE_SECONDS)
                _check_transaction_deadline(deadline)
                token = ("panel-check-" + secrets.token_hex(8)).encode("ascii")
                gesture["echo_request_hex"] = request_packet(0x00, token).hex()
                gesture["status"] = "echo_send_attempted"
                _write_operation_record(log_path, metadata)
                device.send(0x00, token)
                echoed = reader.next(0x80, allow_observed_async_ack=True)
                gesture["echo_packet_hex"] = reader.last_frame.hex()
                if echoed != token or reader.buffer:
                    raise ScopeError("Panel echo token mismatch or trailing response data")
                gesture["status"] = "ack_and_echo_received_execution_unverified"
                metadata["completed_count"] += 1
                _write_operation_record(log_path, metadata)
                if index + 1 < count:
                    time.sleep(PANEL_SETTLE_SECONDS)
            metadata["status"] = "replies_received_execution_unverified"
    except (Exception, KeyboardInterrupt) as error:
        metadata["error"] = str(error) or type(error).__name__
        raise
    finally:
        if reader is not None:
            metadata["asynchronous_ack_packets"] = reader.async_ack_packets
            metadata["received_bytes"] = reader.total
            metadata["frame_count"] = reader.frames
        if wire_path.exists():
            metadata["wire_sha256"] = hashlib.sha256(wire_path.read_bytes()).hexdigest()
        try:
            _write_operation_record(log_path, metadata)
        finally:
            print(json.dumps(metadata, indent=2))


def read_settings(device, log_dir):
    """Preserve one normal SYSData reply without assuming a firmware layout."""
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    base = log_dir / ("read-settings-" + stamp)
    log_path = Path(str(base) + ".json")
    raw_path = Path(str(base) + ".settings.bin")
    wire_path = Path(str(base) + ".wire.bin")
    metadata = {"requested_at_utc": stamp, "command": "read-settings",
                "device": device.metadata, "request_hex": request_packet(0x01).hex(),
                "status": "incomplete", "instrument_settings_changed": False,
                "decoded": False, "settings_verified": False,
                "interpretation": "Raw SYSData only. This firmware's field layout, units and numeric values have not been validated.",
                "log_path": str(log_path.resolve()), "raw_path": str(raw_path.resolve()),
                "wire_path": str(wire_path.resolve())}
    _write_operation_record(log_path, metadata, "x")
    reader = None
    try:
        with wire_path.open("xb") as wire:
            deadline = time.monotonic() + TRANSACTION_SECONDS
            reader = FrameReader(device.read, deadline, wire,
                                 max_wire_bytes=MAX_SETTINGS_BYTES + 5 + 8 * 7,
                                 max_frames=10)
            device.send(0x01)
            answer = reader.next(0x81, allow_observed_async_ack=True)
            with raw_path.open("xb") as raw:
                raw.write(answer)
            metadata.update(payload_bytes=len(answer), payload_hex=answer.hex(),
                            frame_checksum_verified=True,
                            sha256=hashlib.sha256(answer).hexdigest())
            if not answer or len(answer) > MAX_SETTINGS_BYTES:
                raise ScopeError("Settings reply is empty or exceeds one bounded SYSData frame")
            if reader.buffer:
                raise ScopeError("Unexpected trailing settings response data")
            metadata["status"] = "complete_raw_uninterpreted"
    except (Exception, KeyboardInterrupt) as error:
        metadata["error"] = str(error) or type(error).__name__
        raise
    finally:
        if reader is not None:
            metadata["asynchronous_ack_packets"] = reader.async_ack_packets
            metadata["received_bytes"] = reader.total
            metadata["frame_count"] = reader.frames
        if wire_path.exists():
            metadata["wire_sha256"] = hashlib.sha256(wire_path.read_bytes()).hexdigest()
        try:
            _write_operation_record(log_path, metadata)
        finally:
            print(json.dumps(metadata, indent=2))


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--guid", help="Override HANTEK_INTERFACE_GUID or the dedicated WinUSB interface GUID")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("identify", help="Read USB descriptors; no scope protocol command")
    commands.add_parser("echo", help="One unique normal-protocol echo test")
    commands.add_parser("controls", help="List named ordinary controls; never accesses USB")
    panel = commands.add_parser("panel-control", help="Send a named ordinary panel gesture; verify the scope screen")
    panel.add_argument("control", help="Named control ID from the offline controls catalog")
    panel.add_argument("--count", type=int, default=1, help="Rotary gestures 1..5; buttons exactly 1")
    panel.add_argument("--log-dir", type=output_directory, default=DEFAULT_LOG_DIR)
    settings = commands.add_parser("read-settings", help="Save bounded raw SYSData; no numeric decoding")
    settings.add_argument("--log-dir", type=output_directory, default=DEFAULT_LOG_DIR)
    for action in ("acquisition-start", "acquisition-stop"):
        action_parser = commands.add_parser(
            action, help="Explicitly change oscilloscope acquisition; never operates a CNC")
        action_parser.add_argument("--log-dir", type=output_directory,
                                   default=DEFAULT_LOG_DIR)
    capture = commands.add_parser("screenshot", help="Request screen pixels; do not change acquisition")
    capture.add_argument("--output-dir", type=output_directory, default=DEFAULT_CAPTURE_DIR)
    capture.add_argument("--pixel-order", choices=("little", "big"), default="little")
    decode = commands.add_parser("decode", help="Offline RGB565 to PNG; never accesses USB")
    decode.add_argument("raw", type=Path)
    decode.add_argument("png", type=Path)
    decode.add_argument("--pixel-order", choices=("little", "big"), default="little")
    args = parser.parse_args(argv)
    if args.command == "panel-control":
        try:
            scope_controls.control_spec(args.control, args.count)
        except ValueError as error:
            parser.error(str(error))
    if args.command not in ("decode", "controls"):
        try:
            args.guid = configured_interface_guid(args.guid)
        except ValueError as error:
            parser.error(str(error))
    return args


def main(argv=None):
    args = parse_arguments(argv)
    if args.command == "controls":
        print(json.dumps(scope_controls.public_catalog(), indent=2))
        return
    if args.command == "decode":
        pixels = args.raw.read_bytes()
        with args.png.open("xb") as output:
            output.write(rgb565_png(pixels, byte_order=args.pixel_order))
        print(json.dumps({"png": str(args.png.resolve()), "hardware_access": False}))
        return
    with WinUsbScope(args.guid) as scope:
        if args.command == "identify":
            print(json.dumps(scope.metadata, indent=2))
        elif args.command == "echo":
            token = ("scope-check-" + secrets.token_hex(8)).encode("ascii")
            deadline = time.monotonic() + TRANSACTION_SECONDS
            scope.send(0x00, token)
            reader = FrameReader(scope.read, deadline)
            reply = reader.next(0x80)
            if reply != token or reader.buffer:
                raise ScopeError("Echo token mismatch or trailing response")
            print(json.dumps({"echo": "ok", "token": token.decode(),
                              "instrument_settings_changed": False}))
        elif args.command == "panel-control":
            panel_control(scope, args.control, args.count, args.log_dir)
        elif args.command == "read-settings":
            read_settings(scope, args.log_dir)
        elif args.command in ("acquisition-start", "acquisition-stop"):
            args.log_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            log_path = args.log_dir / (args.command + "-" + stamp + ".json")
            payload = b"\x00\x00" if args.command == "acquisition-start" else b"\x00\x01"
            metadata = {"requested_at_utc": stamp, "command": args.command,
                        "target": "oscilloscope acquisition only; no CNC function",
                        "device": scope.metadata,
                        "request_hex": request_packet(0x12, payload).hex(),
                        "status": "prepared", "instrument_state_verified": False,
                        "ack_semantics": "Known short 0x92 replies are collected until a 3-second USB idle timeout. Idle and acknowledgements do not verify execution; verify the scope display.",
                        "log_path": str(log_path.resolve())}
            # Create the review record before sending the state-changing request.
            with log_path.open("x", encoding="utf-8") as log:
                json.dump(metadata, log, indent=2)
            try:
                deadline = time.monotonic() + TRANSACTION_SECONDS
                metadata["status"] = "send_attempted_result_unknown"
                scope.send(0x12, payload)
                reader = FrameReader(scope.read, deadline)
                metadata["acknowledgements"] = []
                acquisition_acknowledgements(reader, metadata["acknowledgements"])
                metadata["status"] = "replies_received_usb_idle_execution_unverified"
            except Exception as exc:
                metadata["error"] = str(exc)
                raise
            finally:
                with log_path.open("w", encoding="utf-8") as log:
                    json.dump(metadata, log, indent=2)
                print(json.dumps(metadata, indent=2))
        elif args.command == "screenshot":
            args.output_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            base = args.output_dir / ("scope-" + stamp)
            raw_path, wire_path = Path(str(base) + ".rgb565"), Path(str(base) + ".wire.bin")
            png_path, json_path = Path(str(base) + ".png"), Path(str(base) + ".json")
            metadata = {"started_utc": stamp, "device": scope.metadata,
                        "instrument_settings_changed": False,
                        "request_hex": request_packet(0x20).hex(),
                        "raw_path": str(raw_path.resolve()),
                        "wire_path": str(wire_path.resolve()),
                        "decode": "RGB565 " + args.pixel_order + " endian; verify against display",
                        "status": "incomplete"}
            try:
                reader = None
                with raw_path.open("xb") as raw, wire_path.open("xb") as wire:
                    deadline = time.monotonic() + TRANSACTION_SECONDS
                    scope.send(0x20)
                    reader = FrameReader(scope.read, deadline, wire)
                    pixels = screenshot_pixels(reader, raw)
                with png_path.open("xb") as png:
                    png.write(rgb565_png(pixels, byte_order=args.pixel_order))
                metadata.update(status="complete", width=WIDTH, height=HEIGHT,
                                bytes=len(pixels), frame_count=reader.frames,
                                sha256=hashlib.sha256(pixels).hexdigest(),
                                png_path=str(png_path.resolve()),
                                packet_and_bulk_checksums="verified")
            except Exception as exc:
                metadata["error"] = str(exc)
                raise
            finally:
                if reader is not None:
                    metadata["asynchronous_ack_packets"] = reader.async_ack_packets
                with json_path.open("x", encoding="utf-8") as log:
                    json.dump(metadata, log, indent=2)
                print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ScopeError, OSError, ValueError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
