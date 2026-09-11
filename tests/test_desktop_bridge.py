"""Offline desktop adapter checks. No test opens a physical USB device."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import desktop_bridge as bridge
import hantek_scope as scope


class DesktopBridgeChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.environment = mock.patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.hardware = mock.patch.object(scope, "WinUsbScope")
        self.device = self.hardware.start()
        self.addCleanup(self.hardware.stop)
        self.device.side_effect = AssertionError("Offline adapter test attempted USB access")

    def run_bridge(self, request=None, *, raw=None, arguments=None):
        if raw is None:
            raw = json.dumps(request).encode("utf-8")
        output = io.StringIO()
        leaked_stdout = io.StringIO()
        leaked_stderr = io.StringIO()
        with contextlib.redirect_stdout(leaked_stdout), contextlib.redirect_stderr(leaked_stderr):
            code = bridge.main([] if arguments is None else arguments,
                               io.BytesIO(raw), output)
        self.assertEqual(code, 0)
        self.assertEqual(leaked_stdout.getvalue(), "")
        self.assertEqual(leaked_stderr.getvalue(), "")
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        return json.loads(output.getvalue())

    @staticmethod
    def client_result(arguments):
        print(json.dumps({"arguments": arguments, "instrument_state_verified": False}, indent=2))

    def test_all_actions_translate_to_only_allowed_cli_arguments(self):
        for action in bridge.ACTIONS:
            with self.subTest(action=action), mock.patch.object(scope, "main", side_effect=self.client_result) as client:
                request = {"action": action}
                expected = ["--guid", scope.DEFAULT_INTERFACE_GUID, action]
                if action == "controls":
                    expected = ["controls"]
                elif action == "screenshot":
                    request["output_dir"] = str(self.root / "captures")
                    expected += ["--output-dir", str(self.root / "captures")]
                elif action in bridge.LOG_ACTIONS:
                    if action == "panel-control":
                        request.update(control="ch1-scale-plus", count=2)
                        expected += ["ch1-scale-plus", "--count", "2"]
                    request["log_dir"] = str(self.root / "logs")
                    expected += ["--log-dir", str(self.root / "logs")]
                response = self.run_bridge(request)
                self.assertEqual(response, {"ok": True, "result": {
                    "arguments": expected, "instrument_state_verified": False}})
                client.assert_called_once_with(expected)
        self.device.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_unknown_actions_keys_and_wrong_types_rejected_before_client(self):
        cases = [None, [], {}, {"action": "decode"}, {"action": "raw"},
                 {"action": ["identify"]}, {"action": 1},
                 {"action": "identify", "command": "reset"},
                 {"action": "identify", "guid": None},
                 {"action": "identify", "guid": 12},
                 {"action": "identify", "guid": ""},
                 {"action": "identify", "guid": "invalid"},
                 {"action": "screenshot"}, {"action": "acquisition-start"},
                 {"action": "acquisition-stop"},
                 {"action": "identify", "output_dir": str(self.root)},
                 {"action": "echo", "log_dir": str(self.root)},
                 {"action": "screenshot", "output_dir": str(self.root), "pixel_order": "big"},
                 {"action": "screenshot", "output_dir": str(self.root), "log_dir": str(self.root)}]
        cases += [{"action": "read-settings"}, {"action": "panel-control", "log_dir": str(self.root)},
                  {"action": "controls", "guid": scope.DEFAULT_INTERFACE_GUID},
                  {"action": "identify", "count": 1}, {"action": "echo", "control": "autoset"}]
        for control, count in [("default-setup", 1), ("utility-menu", 1), (19, 1),
                               ("ch1-scale-plus", 0), ("ch1-scale-plus", 6),
                               ("ch1-scale-plus", True), ("ch1-scale-plus", 1.0),
                               ("ch1-scale-plus", "1"), ("autoset", 2)]:
            cases.append({"action": "panel-control", "control": control, "count": count,
                          "log_dir": str(self.root)})
        with mock.patch.object(scope, "main") as client:
            for request in cases:
                with self.subTest(request=request):
                    response = self.run_bridge(request)
                    self.assertFalse(response["ok"])
                    self.assertIsInstance(response["error"], str)
                    self.assertNotIn("result", response)
            client.assert_not_called()
        self.device.assert_not_called()

    def test_invalid_directory_values_rejected_before_client(self):
        file_path = self.root / "file.txt"
        file_path.write_text("fixture", encoding="utf-8")
        invalid = [None, False, [], "", "relative", "~", "bad\x00path",
                   str(file_path), str(file_path / "child")]
        if os.name == "nt":
            invalid += [r"\\server\share\capture", r"\\?\C:\capture", "C:relative",
                        r"C:\bad:name", r"C:\capture\NUL", r"C:\capture\CON.txt",
                        "C:\\capture\\trailing.", "C:\\capture\\trailing ",
                        r"C:\capture\..\elsewhere"]
        with mock.patch.object(scope, "main") as client:
            for value in invalid:
                with self.subTest(value=value):
                    self.assertFalse(self.run_bridge({"action": "screenshot", "output_dir": value})["ok"])
                    self.assertFalse(self.run_bridge({"action": "acquisition-stop", "log_dir": value})["ok"])
            client.assert_not_called()
        self.device.assert_not_called()

    def test_guid_precedence_and_invalid_environment_before_client(self):
        other = "A31AB777-5893-4A2A-9669-7E9440253BDF"
        with mock.patch.dict(os.environ, {"HANTEK_INTERFACE_GUID": "invalid"}), \
                mock.patch.object(scope, "main", side_effect=self.client_result) as client:
            self.assertFalse(self.run_bridge({"action": "identify"})["ok"])
            client.assert_not_called()
            response = self.run_bridge({"action": "identify", "guid": "{" + other + "}"})
            self.assertEqual(response["result"]["arguments"][:2], ["--guid", other.lower()])
        with mock.patch.dict(os.environ, {"HANTEK_INTERFACE_GUID": other}), \
                mock.patch.object(scope, "main", side_effect=self.client_result):
            response = self.run_bridge({"action": "identify"})
            self.assertEqual(response["result"]["arguments"][:2], ["--guid", other.lower()])

    def test_request_framing_encoding_duplicates_and_size(self):
        cases = [b"", b"{}\n{}", b'{"action":"identify"} trailing', b"\xff",
                 b'{"action":"identify","action":"echo"}',
                 b'{"action":"identify","guid":NaN}',
                 b'{"action":"identify","guid":Infinity}',
                 b"[" * 2000 + b"]" * 2000,
                 b" " * (bridge.MAX_REQUEST_BYTES + 1)]
        with mock.patch.object(scope, "main") as client:
            for raw in cases:
                with self.subTest(raw=raw[:70]):
                    self.assertFalse(self.run_bridge(raw=raw)["ok"])
            client.assert_not_called()
        raw = b'{"action":"identify"}'
        with mock.patch.object(scope, "main", side_effect=self.client_result) as client:
            response = self.run_bridge(raw=raw + b" " * (bridge.MAX_REQUEST_BYTES - len(raw)))
            self.assertTrue(response["ok"])
            client.assert_called_once()
        self.device.assert_not_called()

    def test_reader_never_requests_more_than_limit_plus_one(self):
        stream = mock.Mock()
        stream.read.return_value = b" " * (bridge.MAX_REQUEST_BYTES + 1)
        with self.assertRaises(bridge.RequestError):
            bridge.read_request(stream)
        stream.read.assert_called_once_with(bridge.MAX_REQUEST_BYTES + 1)

    def test_failed_capture_and_acquisition_metadata_remain_unchanged(self):
        for action in ("screenshot", "acquisition-start", "acquisition-stop"):
            evidence = {"status": "incomplete" if action == "screenshot" else "send_attempted_result_unknown",
                        "error": "USB timeout", "instrument_state_verified": False,
                        "wire_path": str(self.root / "partial.wire.bin"),
                        "log_path": str(self.root / "operation.json")}

            def fail(arguments):
                print(json.dumps(evidence, indent=2))
                print("diagnostic text", file=sys.stderr)
                raise scope.ScopeError("USB timeout\nRetained evidence")

            with self.subTest(action=action), mock.patch.object(scope, "main", side_effect=fail) as client:
                directory_key = "output_dir" if action == "screenshot" else "log_dir"
                response = self.run_bridge({"action": action, directory_key: str(self.root)})
                self.assertEqual(response, {"ok": False, "error": "USB timeout Retained evidence", "result": evidence})
                client.assert_called_once()

    def test_client_errors_without_json_and_unexpected_output_are_framed(self):
        for error in (scope.ScopeError("No scope"), OSError("Access denied"),
                      SystemExit(2), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__), \
                    mock.patch.object(scope, "main", side_effect=error) as client:
                response = self.run_bridge({"action": "identify"})
                self.assertFalse(response["ok"])
                self.assertNotIn("result", response)
                client.assert_called_once()
        for text in ("", "diagnostic\n{}", "{}\n{}", "[]", '{"bad":NaN}'):
            with self.subTest(text=text), mock.patch.object(scope, "main", side_effect=lambda args: print(text)):
                self.assertFalse(self.run_bridge({"action": "identify"})["ok"])

    def test_self_test_reports_capabilities_without_stdin_or_usb(self):
        stream = mock.Mock()
        stream.read.side_effect = AssertionError("self-test read stdin")
        output = io.StringIO()
        with mock.patch.object(scope, "main") as client, \
                mock.patch.dict(os.environ, {"HANTEK_INTERFACE_GUID": "invalid"}):
            self.assertEqual(bridge.main(["--self-test"], stream, output), 0)
            client.assert_not_called()
        stream.read.assert_not_called()
        self.device.assert_not_called()
        response = json.loads(output.getvalue())
        self.assertTrue(response["ok"])
        self.assertFalse(response["result"]["hardware_access"])
        self.assertEqual(response["result"]["actions"], list(bridge.ACTIONS))
        self.assertEqual(response["result"]["limits"]["max_request_bytes"], 16384)
        self.assertEqual(response["result"]["protocol_version"], 1)
        self.assertEqual(response["result"]["device"]["vid"], "049F")

    def test_command_line_passthrough_is_rejected_before_client(self):
        with mock.patch.object(scope, "main") as client:
            for arguments in (["identify"], ["--guid", scope.DEFAULT_INTERFACE_GUID],
                              ["--self-test", "extra"], ["--help"]):
                self.assertFalse(self.run_bridge(arguments=arguments)["ok"])
            client.assert_not_called()
        self.device.assert_not_called()

    def test_existing_identify_client_integrates_using_mock_device_only(self):
        metadata = {"vid": "049F", "pid": "505A", "interface_number": 0}
        self.device.side_effect = None
        self.device.return_value.__enter__.return_value.metadata = metadata
        response = self.run_bridge({"action": "identify"})
        self.assertEqual(response, {"ok": True, "result": metadata})
        self.device.assert_called_once_with(scope.DEFAULT_INTERFACE_GUID)
        self.device.return_value.__enter__.assert_called_once()
        self.device.return_value.__exit__.assert_called_once_with(None, None, None)

    def test_actual_controls_catalog_is_offline_even_with_invalid_guid_environment(self):
        with mock.patch.dict(os.environ, {"HANTEK_INTERFACE_GUID": "invalid"}):
            response = self.run_bridge({"action": "controls"})
        self.assertTrue(response["ok"])
        self.assertFalse(response["result"]["hardware_access"])
        self.assertEqual(response["result"]["schema_version"], 1)
        self.assertEqual(len(response["result"]["controls"]), 39)
        self.assertTrue(all("keycode" not in entry for entry in response["result"]["controls"]))
        self.device.assert_not_called()


if __name__ == "__main__":
    unittest.main()
