"""Offline controls and raw-settings checks; all device behavior is synthetic."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import hantek_scope as scope
import scope_controls as controls


def reply(command, payload):
    frame = b"\x53" + struct.pack("<H", len(payload) + 2) + bytes((command,)) + payload
    return frame + bytes((sum(frame) & 255,))


class FakeDevice:
    metadata = {"vid": "049F", "pid": "505A", "fixture": True}

    def __init__(self, root, *, ack=b"\x01", echo=None, settings=b"\x10\x20\x30",
                 asynchronous=False, fail_key=None):
        self.root, self.ack, self.echo, self.settings = root, ack, echo, settings
        self.asynchronous, self.fail_key = asynchronous, fail_key
        self.calls, self.pending, self.before_send = [], [], []
        self.keys = 0

    def send(self, command, payload=b""):
        self.calls.append((command, payload))
        if command == 0x13:
            self.keys += 1
            record = json.loads(next(self.root.glob("panel-control-*.json")).read_text())
            self.before_send.append(record)
            if self.keys == self.fail_key:
                raise OSError("synthetic incomplete USB write")
            data = reply(0x93, self.ack)
        elif command == 0:
            data = reply(0x80, payload if self.echo is None else self.echo)
        elif command == 1:
            data = reply(0x81, self.settings)
        else:
            raise AssertionError("Unexpected device command")
        if self.asynchronous:
            data = reply(0x92, b"\x01\x00") + data
        self.pending += [data[:2], data[2:]]

    def read(self):
        if not self.pending:
            raise OSError(121, "synthetic idle timeout")
        return self.pending.pop(0)


class ControlChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def invoke(self, function, *args, error=None):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), mock.patch.object(scope.time, "sleep"):
            if error:
                with self.assertRaises(error):
                    function(*args)
            else:
                function(*args)
        metadata = json.loads(captured.getvalue())
        self.assertEqual(json.loads(Path(metadata["log_path"]).read_text()), metadata)
        return metadata

    def test_catalog_has_unique_ordinary_keys_and_sanitized_public_data(self):
        catalog = controls.load_catalog()
        self.assertEqual(len(catalog["controls"]), 39)
        keys = {entry["keycode"] for entry in catalog["controls"]}
        self.assertEqual(keys, controls.ORDINARY_KEYCODES)
        self.assertTrue(keys.isdisjoint({0x0b, 0x0e, 0x13, 0x14, 0x15, 0x16, 0x30}))
        self.assertTrue(all("keycode" not in item for item in controls.public_catalog()["controls"]))
        for entry in catalog["controls"]:
            packet = scope.request_packet(0x13, bytes((entry["keycode"], 1)))
            self.assertEqual(packet[:4], b"\x53\x04\x00\x13")
            self.assertEqual(packet[-1], sum(packet[:-1]) & 255)

    def test_low_level_allowlist_refuses_all_other_keys_counts_and_debug_commands(self):
        for key in range(256):
            if key not in controls.ORDINARY_KEYCODES:
                with self.assertRaises(scope.ScopeError):
                    scope.request_packet(0x13, bytes((key, 1)))
        for payload in (b"", b"\x1d", b"\x1d\x00", b"\x1d\x02", b"\x1d\x01\x00"):
            with self.assertRaises(scope.ScopeError):
                scope.request_packet(0x13, payload)
        for command in (0x10, 0x11, 0x14, 0x21, 0x40, 0x43, 0x7f):
            with self.assertRaises(scope.ScopeError):
                scope.request_packet(command)
        self.assertEqual(scope.request_packet(1).hex(), "5302000156")
        with self.assertRaises(scope.ScopeError):
            scope.request_packet(1, b"\x00")

    def test_unknown_controls_and_bad_counts_fail_before_device_construction(self):
        for control, count in (("default-setup", "1"), ("ch1-scale-plus", "0"),
                               ("ch1-scale-plus", "6"), ("autoset", "2"),
                               ("ch1-scale-plus", "1.5"), ("29", "1")):
            with self.subTest(control=control, count=count), \
                    mock.patch.object(scope, "WinUsbScope") as hardware, \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    scope.main(["panel-control", control, "--count", count])
                hardware.assert_not_called()

    def test_rotary_count_is_exact_and_each_attempt_is_logged_before_send(self):
        device = FakeDevice(self.root)
        result = self.invoke(scope.panel_control, device, "ch1-scale-plus", 5, self.root)
        self.assertEqual(device.calls[::2], [(0x13, b"\x1d\x01")] * 5)
        self.assertEqual([c[0] for c in device.calls[1::2]], [0] * 5)
        for index, record in enumerate(device.before_send, 1):
            self.assertEqual(record["send_attempted_count"], index)
            self.assertEqual(record["sent_count"], index - 1)
            self.assertEqual(record["completed_count"], index - 1)
            self.assertEqual(record["gesture_records"][-1]["status"], "send_attempted_result_unknown")
        for field in ("send_attempted_count", "sent_count", "acknowledged_count", "completed_count"):
            self.assertEqual(result[field], 5)
        self.assertFalse(result["instrument_state_verified"])
        self.assertEqual(result["status"], "replies_received_execution_unverified")
        self.assertEqual(result["gesture_records"][0]["menu_id_before_action"], 1)
        self.assertGreater(Path(result["wire_path"]).stat().st_size, 0)

    def test_only_exact_observed_status_packets_are_allowed_around_panel_replies(self):
        device = FakeDevice(self.root, asynchronous=True)
        result = self.invoke(scope.panel_control, device, "timebase-minus", 2, self.root)
        self.assertEqual(result["asynchronous_ack_packets"], ["530400920100ea"] * 4)
        self.assertEqual(result["completed_count"], 2)

    def test_unexpected_ack_shape_stops_without_echo_or_repeat(self):
        device = FakeDevice(self.root, ack=b"\x00\x01")
        result = self.invoke(scope.panel_control, device, "ch1-scale-plus", 5, self.root, error=scope.ScopeError)
        self.assertEqual(device.calls, [(0x13, b"\x1d\x01")])
        self.assertEqual(result["sent_count"], 1)
        self.assertEqual(result["completed_count"], 0)
        self.assertEqual(result["gesture_records"][0]["ack_payload_hex"], "0001")

    def test_echo_failure_does_not_repeat_or_send_remaining_requested_steps(self):
        device = FakeDevice(self.root, echo=b"wrong-token")
        result = self.invoke(scope.panel_control, device, "timebase-plus", 5, self.root, error=scope.ScopeError)
        self.assertEqual([call[0] for call in device.calls], [0x13, 0])
        self.assertEqual(result["acknowledged_count"], 1)
        self.assertEqual(result["completed_count"], 0)
        self.assertIn("echo token mismatch", result["error"])

    def test_panel_settles_after_ack_before_its_single_echo(self):
        device = FakeDevice(self.root)
        observations = []

        def settle(seconds):
            record = json.loads(next(self.root.glob("panel-control-*.json")).read_text())
            observations.append((seconds, list(device.calls), record["acknowledged_count"],
                                 record["gesture_records"][-1]["status"]))

        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(scope.time, "sleep", side_effect=settle):
            scope.panel_control(device, "ch1-scale-minus", 1, self.root)
        self.assertEqual(observations, [(0.2, [(0x13, b"\x1c\x01")], 1,
                                         "acknowledged_execution_unverified")])
        self.assertEqual([call[0] for call in device.calls], [0x13, 0])

    def test_deadline_expiring_during_settle_prevents_followup_echo(self):
        device = FakeDevice(self.root)
        clock = [0.0]

        def settle(seconds):
            clock[0] = 31.0

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), mock.patch.object(scope.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(scope.time, "sleep", side_effect=settle), self.assertRaisesRegex(scope.ScopeError, "deadline"):
            scope.panel_control(device, "ch1-scale-minus", 1, self.root)
        result = json.loads(captured.getvalue())
        self.assertEqual(device.calls, [(0x13, b"\x1c\x01")])
        self.assertEqual(result["acknowledged_count"], 1)
        self.assertEqual(result["completed_count"], 0)

    def test_partial_send_counts_remain_distinct_and_stop_sequence(self):
        device = FakeDevice(self.root, fail_key=2)
        result = self.invoke(scope.panel_control, device, "trigger-level-plus", 5, self.root, error=OSError)
        self.assertEqual(result["send_attempted_count"], 2)
        self.assertEqual(result["sent_count"], 1)
        self.assertEqual(result["acknowledged_count"], 1)
        self.assertEqual(result["completed_count"], 1)
        self.assertEqual([call[0] for call in device.calls], [0x13, 0, 0x13])

    def test_log_failure_prevents_first_key(self):
        device = FakeDevice(self.root)
        original = scope._write_operation_record

        def fail_before_send(path, metadata, mode="w"):
            if mode != "x" and metadata["send_attempted_count"]:
                raise OSError("synthetic full disk")
            original(path, metadata, mode)

        with mock.patch.object(scope, "_write_operation_record", side_effect=fail_before_send), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(OSError):
            scope.panel_control(device, "autoset", 1, self.root)
        self.assertEqual(device.calls, [])

    def test_transaction_deadline_prevents_an_additional_gesture(self):
        device = FakeDevice(self.root)
        with mock.patch.object(scope, "_check_transaction_deadline", side_effect=scope.ScopeError("deadline")):
            result = self.invoke(scope.panel_control, device, "autoset", 1, self.root, error=scope.ScopeError)
        self.assertEqual(device.calls, [])
        self.assertEqual(result["send_attempted_count"], 0)

    def test_raw_settings_keeps_exact_bytes_and_reports_no_decoding(self):
        payload = bytes(range(256)) * 4
        device = FakeDevice(self.root, settings=payload, asynchronous=True)
        result = self.invoke(scope.read_settings, device, self.root)
        self.assertEqual(device.calls, [(1, b"")])
        self.assertEqual(bytes.fromhex(result["payload_hex"]), payload)
        self.assertEqual(Path(result["raw_path"]).read_bytes(), payload)
        self.assertEqual(result["status"], "complete_raw_uninterpreted")
        self.assertTrue(result["frame_checksum_verified"])
        self.assertFalse(result["decoded"])
        self.assertFalse(result["settings_verified"])
        self.assertFalse(result["instrument_settings_changed"])

    def test_empty_settings_retains_evidence_and_fails(self):
        device = FakeDevice(self.root, settings=b"")
        result = self.invoke(scope.read_settings, device, self.root, error=scope.ScopeError)
        self.assertEqual(result["payload_bytes"], 0)
        self.assertEqual(Path(result["wire_path"]).read_bytes(), reply(0x81, b""))
        self.assertEqual(result["status"], "incomplete")

    def test_settings_rejects_corrupt_frames_and_retains_wire(self):
        device = FakeDevice(self.root)
        device.read = lambda: reply(0x81, b"raw")[:-1] + b"\x00"
        result = self.invoke(scope.read_settings, device, self.root, error=scope.ScopeError)
        self.assertIn("checksum", result["error"])
        self.assertFalse(Path(result["raw_path"]).exists())
        self.assertGreater(Path(result["wire_path"]).stat().st_size, 0)

    def test_new_reader_limits_are_enforced_without_weakening_defaults(self):
        source = scope.FrameReader(lambda: b"x" * 6, time.monotonic() + 10, max_wire_bytes=5)
        with self.assertRaisesRegex(scope.ScopeError, "bounded"):
            source.next(0x81)
        source = scope.FrameReader(lambda: reply(0x81, b"x"), time.monotonic() + 10, max_frames=0)
        with self.assertRaisesRegex(scope.ScopeError, "Too many"):
            source.next(0x81)
        self.assertEqual(scope.FrameReader(lambda: b"", 0).max_wire_bytes, scope.MAX_WIRE_BYTES)


if __name__ == "__main__":
    unittest.main()
