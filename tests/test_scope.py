"""Offline protocol checks. This suite never instantiates WinUsbScope."""
import io
import contextlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest import mock
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import hantek_scope as scope


def reply(command, payload):
    frame = b"\x53" + struct.pack("<H", len(payload) + 2) + bytes((command,)) + payload
    return frame + bytes((sum(frame) & 255,))


def reader(blocks):
    iterator = iter(blocks)
    return scope.FrameReader(lambda: next(iterator, b""), time.monotonic() + 5)


class ConfigurationChecks(unittest.TestCase):
    def test_guid_precedence_and_normalization(self):
        other_guid = "A31AB777-5893-4A2A-9669-7E9440253BDF"
        self.assertEqual(scope.configured_interface_guid(environ={}), scope.DEFAULT_INTERFACE_GUID)
        self.assertEqual(scope.configured_interface_guid(environ={"HANTEK_INTERFACE_GUID": "{" + other_guid + "}"}),
                         other_guid.lower())
        self.assertEqual(scope.configured_interface_guid(scope.DEFAULT_INTERFACE_GUID,
                                                        {"HANTEK_INTERFACE_GUID": "invalid"}),
                         scope.DEFAULT_INTERFACE_GUID)
        for invalid in ("", "invalid", "{not-a-guid}"):
            with self.assertRaises(ValueError):
                scope.configured_interface_guid(environ={"HANTEK_INTERFACE_GUID": invalid})

    def test_invalid_guid_is_rejected_before_usb_access(self):
        with mock.patch.dict(os.environ, {"HANTEK_INTERFACE_GUID": "invalid"}), \
                mock.patch.object(scope, "WinUsbScope") as hardware, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                scope.main(["identify"])
            self.assertEqual(error.exception.code, 2)
            hardware.assert_not_called()
        with mock.patch.object(scope, "WinUsbScope") as hardware, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                scope.main(["--guid", "invalid", "identify"])
            hardware.assert_not_called()

    def test_paths_follow_repo_defaults_and_calling_project_overrides(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.dict(os.environ, {"HANTEK_INTERFACE_GUID": scope.DEFAULT_INTERFACE_GUID}):
            try:
                os.chdir(folder)
                capture = scope.parse_arguments(["screenshot"])
                action = scope.parse_arguments(["acquisition-stop"])
                self.assertEqual(capture.output_dir, Path(scope.__file__).resolve().parents[1] / "artifacts" / "captures")
                self.assertEqual(action.log_dir, Path(scope.__file__).resolve().parents[1] / "artifacts" / "logs")
                self.assertEqual(scope.parse_arguments(["screenshot", "--output-dir", "results/captures"]).output_dir,
                                 Path(folder).resolve() / "results" / "captures")
                self.assertEqual(scope.parse_arguments(["acquisition-start", "--log-dir", "results/logs"]).log_dir,
                                 Path(folder).resolve() / "results" / "logs")
            finally:
                os.chdir(original_cwd)

    def test_offline_decode_does_not_require_usb_configuration(self):
        with mock.patch.dict(os.environ, {"HANTEK_INTERFACE_GUID": "invalid"}):
            args = scope.parse_arguments(["decode", "input.rgb565", "output.png"])
        self.assertEqual(args.command, "decode")


class ProtocolChecks(unittest.TestCase):
    def test_exact_documented_request_and_allowlist(self):
        self.assertEqual(scope.request_packet(0x20), bytes.fromhex("53 02 00 20 75"))
        self.assertEqual(scope.request_packet(0), bytes.fromhex("53 02 00 00 55"))
        for command in (0x11, 0x12, 0x13, 0x7F):
            with self.assertRaises(scope.ScopeError):
                scope.request_packet(command)

    def test_only_explicit_scope_acquisition_payloads(self):
        self.assertEqual(scope.request_packet(0x12, b"\x00\x00"),
                         bytes.fromhex("53 04 00 12 00 00 69"))
        self.assertEqual(scope.request_packet(0x12, b"\x00\x01"),
                         bytes.fromhex("53 04 00 12 00 01 6a"))
        for payload in (b"", b"\x00", b"\x01\x00", b"\x01\x01", b"\x00\x02", b"\x00\x00\x00"):
            with self.assertRaises(scope.ScopeError):
                scope.request_packet(0x12, payload)
        acknowledgement = reply(0x92, b"\x00")
        source = reader([acknowledgement])
        self.assertEqual(source.next(0x92), b"\x00")
        self.assertEqual(source.last_frame, acknowledgement)

    def test_fragmented_and_coalesced_frames(self):
        a, b = reply(0x80, b"first"), reply(0x80, b"second")
        source = reader([a[:2], a[2:6], a[6:] + b])
        self.assertEqual(source.next(0x80), b"first")
        self.assertEqual(source.next(0x80), b"second")
        self.assertFalse(source.buffer)

    def test_corrupt_frame_fails(self):
        packet = bytearray(reply(0x80, b"hello"))
        packet[-1] ^= 1
        with self.assertRaisesRegex(scope.ScopeError, "checksum"):
            reader([packet]).next(0x80)
        with self.assertRaisesRegex(scope.ScopeError, "command"):
            reader([reply(0xA0, b"hello")]).next(0x80)
        with self.assertRaisesRegex(scope.ScopeError, "empty"):
            reader([reply(0x80, b"hello")[:4]]).next(0x80)

    def test_complete_and_corrupt_screenshot(self):
        pixels = bytes(range(256)) * (scope.MAX_IMAGE_BYTES // 256)
        data = [reply(0xA0, b"\x01" + pixels[i:i + 60000])
                for i in range(0, len(pixels), 60000)]
        terminal = reply(0xA0, bytes((2, sum(pixels) & 255)))
        raw = io.BytesIO()
        self.assertEqual(scope.screenshot_pixels(reader(data + [terminal]), raw), pixels)
        self.assertEqual(raw.getvalue(), pixels)
        corrupt = reply(0xA0, bytes((2, (sum(pixels) + 1) & 255)))
        with self.assertRaisesRegex(scope.ScopeError, "bulk checksum"):
            scope.screenshot_pixels(reader(data + [corrupt]), io.BytesIO())
        with self.assertRaisesRegex(scope.ScopeError, "Expected 768000"):
            scope.screenshot_pixels(reader([reply(0xA0, b"\x01\0\0"),
                                            reply(0xA0, b"\x02\0")]), io.BytesIO())

    def test_rgb565_png_primary_colors_crc_and_scanline(self):
        # Full red, green, blue, white, black in little-endian RGB565.
        pixels = bytes.fromhex("00f8 e007 1f00 ffff 0000")
        png = scope.rgb565_png(pixels, width=5, height=1)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        index, image_data = 8, b""
        while index < len(png):
            size = int.from_bytes(png[index:index + 4], "big")
            kind, data = png[index + 4:index + 8], png[index + 8:index + 8 + size]
            crc = int.from_bytes(png[index + 8 + size:index + 12 + size], "big")
            self.assertEqual(crc, zlib.crc32(kind + data) & 0xFFFFFFFF)
            if kind == b"IDAT":
                image_data += data
            index += 12 + size
        self.assertEqual(zlib.decompress(image_data),
                         b"\0\xff\0\0\0\xff\0\0\0\xff\xff\xff\xff\0\0\0")

    def test_multistage_ack_stops_only_at_idle(self):
        packets = iter([bytes.fromhex("530400920100ea"),
                        bytes.fromhex("5303009200e8")])

        def read_with_idle():
            try:
                return next(packets)
            except StopIteration:
                raise OSError(121, "simulated WinUSB idle timeout")

        source = scope.FrameReader(read_with_idle, time.monotonic() + 5)
        records = []
        scope.acquisition_acknowledgements(source, records)
        self.assertEqual([r["payload_hex"] for r in records], ["0100", "00"])

    def test_strict_reader_never_skips_other_commands(self):
        for packet in (bytes.fromhex("5303009200e8"),
                       reply(0x92, b"\x01image-bearing-data"), reply(0x93, b"\x00")):
            with self.assertRaisesRegex(scope.ScopeError, "command"):
                reader([packet]).next(0xA0)

    def test_screenshot_accepts_only_exact_observed_status_packets(self):
        first = bytes.fromhex("5303009200e8")
        second = bytes.fromhex("530400920100ea")
        source = reader([first + second + reply(0xA0, b"\x01pixels")])
        self.assertEqual(source.next(0xA0, allow_observed_async_ack=True), b"\x01pixels")
        self.assertEqual(source.async_ack_packets, [first.hex(), second.hex()])
        for packet in (reply(0x92, b"\x00\x00"), reply(0x92, b"\x00\x01"),
                       reply(0x92, b"\x01image-bearing-data"), reply(0x93, b"\x00")):
            with self.assertRaisesRegex(scope.ScopeError, "command"):
                reader([packet]).next(0xA0, allow_observed_async_ack=True)
        with self.assertRaisesRegex(scope.ScopeError, "Too many"):
            reader([first * 9]).next(0xA0, allow_observed_async_ack=True)
        with self.assertRaisesRegex(scope.ScopeError, "checksum"):
            reader([first[:-1] + b"\x00"]).next(0xA0, allow_observed_async_ack=True)

    def test_ack_drain_has_exact_payload_allowlist_and_count_bound(self):
        with self.assertRaisesRegex(scope.ScopeError, "Unrecognized"):
            scope.acquisition_acknowledgements(reader([reply(0x92, b"\x02")]), [])
        with self.assertRaisesRegex(scope.ScopeError, "count exceeded"):
            scope.acquisition_acknowledgements(reader([bytes.fromhex("5303009200e8") * 8]), [])

    def test_idle_without_any_ack_is_failure(self):
        def timeout():
            raise OSError(121, "simulated WinUSB idle timeout")
        with self.assertRaises(OSError):
            scope.acquisition_acknowledgements(
                scope.FrameReader(timeout, time.monotonic() + 5), [])


if __name__ == "__main__":
    unittest.main()
