"""File/CLI and adapter integration checks; USB is always forbidden or mocked."""
import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import hantek_scope as scope
import scope_ai as ai
import scope_settings
import scope_setup

IDENTITY = {"vid": "049F", "pid": "505A", "device_version_bcd": "2430"}
TARGET = {"schema_version": 1, "settings": {"ch1.volts_per_div": 2, "trigger.source": "CH1"}}


class AiEntryChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.target_file = self.root / "target.json"

    def write_target(self, data):
        self.target_file.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return self.target_file

    def test_target_file_accepts_utf8_bom_and_canonicalizes_document(self):
        path = self.write_target(b"\xef\xbb\xbf" + json.dumps(TARGET).encode())
        self.assertEqual(ai.load_target(path), {"ch1.volts_per_div": 2.0, "trigger.source": "ch1"})

    def test_duplicate_nested_keys_nonfinite_values_and_unsupported_structure_reject(self):
        invalid = [
            '{"schema_version":1,"schema_version":1,"settings":{"ch1.probe":1}}',
            '{"schema_version":1,"settings":{"ch1.probe":1,"ch1.probe":10}}',
            '{"schema_version":1,"settings":{"trigger.level_volts":NaN}}',
            '{"schema_version":1,"settings":{"trigger.level_volts":Infinity}}',
            '{"schema_version":1,"settings":{"trigger.level_volts":1e999}}',
            '{"schema_version":1,"settings":{"ch1.probe":true}}',
            '{"schema_version":1,"settings":{"ch1":{"probe":1}}}',
            '{"schema_version":1,"settings":{"command":"reset"}}',
            '{"schema_version":1,"settings":{"ch1.probe":1},"raw":"00"}',
            '[]', '{}', '{"schema_version":1,', b'\xff\xfe',
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ai.load_target(self.write_target(value))

    def test_file_reader_requests_only_limit_plus_one_and_rejects_oversize(self):
        class BoundedInput(io.BytesIO):
            requested = None
            def read(self, size=-1):
                self.requested = size
                return super().read(size)
        stream = BoundedInput(b" " * (ai.MAX_TARGET_BYTES + 100))
        with mock.patch.object(Path, "open", return_value=stream), self.assertRaises(ValueError):
            ai.load_target(self.target_file)
        self.assertEqual(stream.requested, ai.MAX_TARGET_BYTES + 1)

    def test_real_offline_cli_commands_never_instantiate_usb_even_with_invalid_guid_env(self):
        self.write_target(json.dumps(TARGET))
        commands = [["setup-capabilities"], ["validate-setup", "--settings-file", str(self.target_file)]]
        with mock.patch.object(scope, "WinUsbScope", side_effect=AssertionError("Offline command tried USB")) as usb, \
                mock.patch.dict(os.environ, {"HANTEK_INTERFACE_GUID": "invalid-offline-guid"}):
            for command in commands:
                with self.subTest(command=command), contextlib.redirect_stdout(io.StringIO()) as output:
                    scope.main(command)
                record = json.loads(output.getvalue())
                if command[0] == "validate-setup":
                    self.assertEqual(record["status"], "valid")
                    self.assertFalse(record["hardware_access"])
                else:
                    self.assertEqual(record["schema_version"], 1)
                    self.assertIn("trigger.level_volts", record["settings"])
            usb.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [self.target_file])

    def test_invalid_configure_is_rejected_before_usb_construction(self):
        requests = [b'{"schema_version":1,"settings":{"ch1.probe":true}}',
                    b'{"schema_version":1,"settings":{"ch1.probe":1,"ch1.probe":10}}',
                    b' ' * (ai.MAX_TARGET_BYTES + 1)]
        with mock.patch.object(scope, "WinUsbScope", side_effect=AssertionError("Invalid setup tried USB")) as usb:
            for content in requests:
                self.write_target(content)
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                    scope.main(["configure", "--settings-file", str(self.target_file)])
                self.assertEqual(raised.exception.code, 2)
            usb.assert_not_called()

    def test_missing_target_and_unknown_cli_switch_reject_before_usb(self):
        self.write_target(json.dumps(TARGET))
        commands = [["configure"], ["configure", "--settings-file", str(self.root / "absent.json")],
                    ["configure", "--settings-file", str(self.target_file), "--raw", "00"]]
        with mock.patch.object(scope, "WinUsbScope") as usb:
            for command in commands:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    scope.main(command)
            usb.assert_not_called()

    def make_client(self):
        raw_path = self.root / "synthetic-protocol.bin"
        raw_path.write_bytes(b"Synthetic profile fixture, validated by a stub only")
        client = mock.Mock()
        client.PANEL_SETTLE_SECONDS = .2
        client.read_protocol.return_value = {"raw_path": str(raw_path), "log_path": "protocol-evidence.json"}
        client.read_settings.return_value = {"payload_hex": "00", "sha256": "0" * 64, "log_path": "settings-evidence.json"}
        client.panel_control.return_value = {"status": "replies_received_execution_unverified"}
        return client

    def test_numeric_setup_refuses_other_usb_revisions_before_protocol_request(self):
        for key, value in [("vid", "0000"), ("pid", "0000"), ("device_version_bcd", "0000"), ("device_version_bcd", None)]:
            with self.subTest(key=key, value=value):
                client = self.make_client()
                identity = {**IDENTITY, key: value}
                driver = ai.SetupDriver(client, SimpleNamespace(metadata=identity), self.root, 200)
                with self.assertRaises(ValueError): driver.initialize()
                client.read_protocol.assert_not_called()
                client.panel_control.assert_not_called()

    def test_protocol_and_settings_settle_before_following_key_without_retries(self):
        client = self.make_client()
        order = []
        protocol_result, settings_result = client.read_protocol.return_value, client.read_settings.return_value
        client.read_protocol.side_effect = lambda *args, **kwargs: order.append("protocol") or protocol_result
        client.read_settings.side_effect = lambda *args, **kwargs: order.append("settings") or settings_result
        client.panel_control.side_effect = lambda *args, **kwargs: order.append("key") or {"status": "sent"}
        client._check_transaction_deadline.side_effect = lambda deadline: order.append("deadline")
        driver = ai.SetupDriver(client, SimpleNamespace(metadata=IDENTITY), self.root, 200)
        with mock.patch.object(scope_settings, "validate_protocol", return_value={"profile": "fixture"}), \
                mock.patch.object(scope_settings, "decode_settings", return_value={"state": {}, "raw_fields": {}}), \
                mock.patch.object(ai.time, "sleep", side_effect=lambda _: order.append("settle")):
            driver.initialize()
            snapshot = driver.read()
            driver.press("ch1-scale-plus")
        self.assertEqual(order, ["protocol", "settle", "deadline", "settings", "settle", "deadline", "key", "settle", "deadline"])
        self.assertTrue(snapshot["profile_validated"])
        self.assertTrue(snapshot["frame_checksum_verified"])
        for name in ("read_protocol", "read_settings", "panel_control"):
            method = getattr(client, name)
            self.assertEqual(method.call_count, 1)
            self.assertIs(method.call_args.kwargs["emit"], False)
            self.assertEqual(method.call_args.kwargs["overall_deadline"], 200)
        self.assertEqual(client.panel_control.call_args.args[1:3], ("ch1-scale-plus", 1))

    def test_failed_or_mismatched_profile_cannot_read_settings_or_send_a_key(self):
        for failure in ("transport", "schema"):
            with self.subTest(failure=failure):
                client = self.make_client()
                if failure == "transport": client.read_protocol.side_effect = OSError("Profile transfer timed out")
                driver = ai.SetupDriver(client, SimpleNamespace(metadata=IDENTITY), self.root, 200)
                with mock.patch.object(scope_settings, "validate_protocol", side_effect=ValueError("Profile does not match")), \
                        self.assertRaises((ValueError, OSError)):
                    driver.initialize()
                self.assertEqual(client.read_protocol.call_count, 1)
                client.read_settings.assert_not_called()
                client.panel_control.assert_not_called()
                self.assertIsNone(driver.profile)

    def test_settlement_deadline_failure_stops_before_following_settings_request(self):
        client = self.make_client()
        client._check_transaction_deadline.side_effect = TimeoutError("Budget expired during settle")
        driver = ai.SetupDriver(client, SimpleNamespace(metadata=IDENTITY), self.root, 200)
        with mock.patch.object(scope_settings, "validate_protocol", return_value={"profile": "fixture"}), \
                mock.patch.object(ai.time, "sleep"), self.assertRaises(TimeoutError):
            driver.initialize()
        self.assertEqual(client.read_protocol.call_count, 1)
        client.read_settings.assert_not_called()
        client.panel_control.assert_not_called()

    def test_uninitialized_driver_cannot_read_interpreted_settings(self):
        client = self.make_client()
        driver = ai.SetupDriver(client, SimpleNamespace(metadata=IDENTITY), self.root, 200)
        with self.assertRaises(ValueError): driver.read()
        client.read_settings.assert_not_called()

    def test_actual_main_settings_and_configure_emit_one_final_json_with_durable_journal(self):
        self.write_target(json.dumps(TARGET))
        for command, failure in [("settings", False), ("configure", False), ("configure", True)]:
            with self.subTest(command=command, failure=failure):
                device = SimpleNamespace(metadata=IDENTITY)
                driver = mock.Mock()
                driver.initialize.return_value = {"profile": "fixture", "validated": True}
                driver.read.return_value = {"profile_validated": True, "frame_checksum_verified": True,
                                            "state": {"ch1.volts_per_div": 2}}
                def configure(instance, target, journal, **kwargs):
                    self.assertIs(instance, driver)
                    self.assertEqual(target, {"ch1.volts_per_div": 2.0, "trigger.source": "ch1"})
                    instance.read()
                    journal({"event": "before_press", "control": "ch1-scale-plus", "step": 1})
                    journal_path = max(self.root.glob("logs/configure-*/journal.jsonl"), key=lambda item: item.stat().st_mtime_ns)
                    persisted = [json.loads(line) for line in journal_path.read_text().splitlines()]
                    self.assertEqual(persisted[-1]["control"], "ch1-scale-plus")
                    instance.press("ch1-scale-plus")
                    if failure:
                        raise scope_setup.SetupError("Send attempted; result unknown", {"status": "aborted", "steps": 1})
                    instance.read()
                    return {"status": "verified", "target": target, "steps": 1}
                args = [command, "--log-dir", str(self.root / "logs")]
                if command == "configure": args += ["--settings-file", str(self.target_file)]
                output = io.StringIO()
                with mock.patch.object(scope, "WinUsbScope") as usb, mock.patch.object(ai, "SetupDriver", return_value=driver), \
                        mock.patch.object(scope_setup, "configure", side_effect=configure), contextlib.redirect_stdout(output):
                    usb.return_value.__enter__.return_value = device
                    if failure:
                        with self.assertRaises(scope_setup.SetupError): scope.main(args)
                    else:
                        scope.main(args)
                    self.assertEqual(usb.call_count, 1)
                record = json.loads(output.getvalue())
                self.assertEqual(json.loads(Path(record["log_path"]).read_text()), record)
                self.assertEqual(record["status"], "aborted" if failure else "complete" if command == "settings" else "verified")
                self.assertEqual(record["settings_verified"], command == "configure" and not failure)
                self.assertEqual(driver.press.call_count, 0 if command == "settings" else 1)
                if failure:
                    self.assertEqual(record["setup"]["steps"], 1)
                    self.assertIn("unknown", record["error"])

    def test_final_record_write_failure_still_emits_one_aborted_json_result(self):
        device = SimpleNamespace(metadata=IDENTITY)
        driver = mock.Mock()
        driver.initialize.return_value = {"profile": "fixture"}
        args = SimpleNamespace(command="configure", log_dir=self.root / "logs", target={"ch1.volts_per_div": 2})
        real_write = scope._write_operation_record
        writes = []
        def failing_final_write(path, record, mode="w"):
            writes.append(mode)
            if mode != "x": raise OSError("Synthetic final audit write failed")
            return real_write(path, record, mode)
        output = io.StringIO()
        with mock.patch.object(ai, "SetupDriver", return_value=driver), \
                mock.patch.object(scope_setup, "configure", return_value={"status": "verified", "steps": 0}), \
                mock.patch.object(scope, "_write_operation_record", side_effect=failing_final_write), \
                contextlib.redirect_stdout(output), self.assertRaises(OSError):
            ai.run(scope, device, args)
        record = json.loads(output.getvalue())
        self.assertEqual(record["status"], "aborted")
        self.assertFalse(record["settings_verified"])
        self.assertIn("audit", record["audit_error"].lower())
        self.assertEqual(writes, ["x", "w"])

    def test_initial_audit_creation_failure_prevents_driver_initialization_and_gestures(self):
        args = SimpleNamespace(command="configure", log_dir=self.root / "logs", target={"ch1.volts_per_div": 2})
        with mock.patch.object(scope, "_write_operation_record", side_effect=OSError("Disk full")), \
                mock.patch.object(ai, "SetupDriver") as driver, \
                mock.patch.object(scope_setup, "configure") as configure, self.assertRaises(OSError):
            ai.run(scope, SimpleNamespace(metadata=IDENTITY), args)
        driver.assert_not_called()
        configure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
