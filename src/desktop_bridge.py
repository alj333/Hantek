"""One bounded JSON request for the desktop app; no shell or raw USB commands.

The caller writes a UTF-8 request, closes stdin, and reads one JSON response line.
``--self-test`` reports build capabilities without reading stdin or opening USB.
"""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path, PureWindowsPath
import platform
import re
import struct
import sys

import hantek_scope as scope


PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 16 * 1024
ACTIONS = ("identify", "echo", "screenshot", "acquisition-start", "acquisition-stop",
           "controls", "panel-control", "read-settings")
REQUEST_KEYS = frozenset(("action", "guid", "output_dir", "log_dir", "control", "count"))
LOG_ACTIONS = ("acquisition-start", "acquisition-stop", "panel-control", "read-settings")


class RequestError(ValueError):
    """An invalid desktop request; no device operation was attempted."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RequestError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _invalid_constant(value):
    raise RequestError("Nonstandard JSON value: " + value)


def _json_object(value):
    parsed = json.loads(value, object_pairs_hook=_unique_object,
                        parse_constant=_invalid_constant)
    if not isinstance(parsed, dict):
        raise RequestError("Expected exactly one JSON object.")
    return parsed


def read_request(stream):
    """Read at most the limit plus one byte, then reject oversize/trailing data."""
    data = stream.read(MAX_REQUEST_BYTES + 1)
    if not isinstance(data, bytes):
        raise RequestError("The request input must be a UTF-8 byte stream.")
    if len(data) > MAX_REQUEST_BYTES:
        raise RequestError("Request exceeds the 16 KiB limit.")
    try:
        return _json_object(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise RequestError("Expected exactly one valid UTF-8 JSON object.") from error


def _check_windows_path(path):
    # Reject UNC, device namespaces and ambiguous Windows filename aliases.
    # The desktop app supplies a local directory chosen by the user.
    windows = PureWindowsPath(path)
    if not re.fullmatch(r"[A-Za-z]:", windows.drive) or windows.root != "\\":
        raise RequestError("Output and log directories must be absolute local drive paths.")
    for part in windows.parts[1:]:
        if (part in (".", "..") or part.endswith((".", " "))
                or re.search(r'[<>:"|?*\x00-\x1f]', part)
                or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?",
                                part, re.IGNORECASE)):
            raise RequestError("Output or log directory contains an unsupported Windows path component.")


def _directory(value, name):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RequestError(name + " must be a nonempty absolute directory path.")
    path = Path(value)
    if not path.is_absolute():
        raise RequestError(name + " must be an absolute directory path.")
    if os.name == "nt":
        _check_windows_path(value)
    path = path.resolve(strict=False)
    if os.name == "nt":
        _check_windows_path(str(path))
    # Validate existing ancestors without creating directories or opening USB.
    ancestor = path
    while not ancestor.exists() and ancestor != ancestor.parent:
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        raise RequestError(name + " points to a file or has a file as its parent.")
    return str(path)


def validated_arguments(request):
    """Translate the complete allowlisted request before any device access."""
    if not isinstance(request, dict):
        raise RequestError("Expected exactly one JSON object.")
    unknown = set(request) - REQUEST_KEYS
    if unknown:
        raise RequestError("Unknown request key: " + ", ".join(sorted(unknown)))
    action = request.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        raise RequestError("Unsupported action. Allowed actions: " + ", ".join(ACTIONS))
    if action == "controls":
        if set(request) != {"action"}:
            raise RequestError("The offline controls action accepts no configuration or other arguments.")
        return ["controls"]
    if action != "panel-control" and ("control" in request or "count" in request):
        raise RequestError("control and count are only valid for panel-control.")
    if action == "panel-control":
        try:
            scope.scope_controls.control_spec(request.get("control"), request.get("count", 1))
        except ValueError as error:
            raise RequestError(str(error)) from error
    if "guid" in request and (not isinstance(request["guid"], str) or not request["guid"].strip()):
        raise RequestError("guid must be a nonempty UUID string.")
    try:
        # Resolve the same explicit/environment/default precedence as the CLI,
        # before entering the client or touching hardware.
        guid = scope.configured_interface_guid(request.get("guid"))
    except (ValueError, AttributeError) as error:
        raise RequestError("Invalid interface GUID configuration.") from error
    if "output_dir" in request and action != "screenshot":
        raise RequestError("output_dir is only valid for screenshot.")
    if "log_dir" in request and action not in LOG_ACTIONS:
        raise RequestError("log_dir is only valid for acquisition, panel-control or read-settings actions.")
    arguments = ["--guid", guid, action]
    if action == "panel-control":
        arguments.extend((request["control"], "--count", str(request.get("count", 1))))
    if action == "screenshot":
        if "output_dir" not in request:
            raise RequestError("screenshot requires output_dir.")
        arguments.extend(("--output-dir", _directory(request["output_dir"], "output_dir")))
    elif action in LOG_ACTIONS:
        if "log_dir" not in request:
            raise RequestError(action + " requires log_dir.")
        arguments.extend(("--log-dir", _directory(request["log_dir"], "log_dir")))
    return arguments


def _explanation(error):
    if isinstance(error, KeyboardInterrupt):
        return "Operation interrupted; the instrument state may be unknown."
    if isinstance(error, SystemExit):
        return "The scope client exited before completing the request."
    return " ".join(str(error).split())[:2048] or type(error).__name__


def handle_request(request):
    try:
        arguments = validated_arguments(request)
    except (Exception, SystemExit) as error:
        return {"ok": False, "error": _explanation(error)}
    captured = io.StringIO()
    captured_errors = io.StringIO()
    failure = None
    # Keep client JSON (including evidence printed in its finally blocks) off
    # protocol stdout. Never retry a failed operation or reinterpret its state.
    with redirect_stdout(captured), redirect_stderr(captured_errors):
        try:
            exit_code = scope.main(arguments)
            if exit_code not in (None, 0):
                raise RuntimeError("The scope client returned an unsuccessful exit code.")
        except (Exception, SystemExit, KeyboardInterrupt) as error:
            failure = error
    try:
        result = _json_object(captured.getvalue())
    except (ValueError, RecursionError):
        result = None
    if failure is not None:
        response = {"ok": False, "error": _explanation(failure)}
        if result is not None:
            response["result"] = result
        return response
    if result is None:
        return {"ok": False, "error": "The scope client did not return exactly one JSON object."}
    return {"ok": True, "result": result}


def self_test():
    """Static build/runtime information only; deliberately does not inspect USB."""
    catalog = scope.scope_controls.public_catalog()
    return {
        "protocol_version": PROTOCOL_VERSION,
        "hardware_access": False,
        "actions": list(ACTIONS),
        "control_catalog": {"schema_version": catalog["schema_version"],
                            "count": len(catalog["controls"]),
                            "validation": catalog["validation"]},
        "runtime": {"python": platform.python_version(),
                    "implementation": platform.python_implementation(),
                    "platform": sys.platform,
                    "pointer_bits": struct.calcsize("P") * 8,
                    "frozen": bool(getattr(sys, "frozen", False))},
        "device": {"vid": "%04X" % scope.VID, "pid": "%04X" % scope.PID,
                   "default_interface_guid": scope.DEFAULT_INTERFACE_GUID},
        "limits": {"max_request_bytes": MAX_REQUEST_BYTES,
                   "transaction_seconds": scope.TRANSACTION_SECONDS,
                   "usb_timeout_ms": scope.TIMEOUT_MS},
        "screenshot": {"width": scope.WIDTH, "height": scope.HEIGHT,
                       "pixel_format": "RGB565 little-endian"},
    }


def main(argv=None, input_stream=None, output_stream=None):
    arguments = sys.argv[1:] if argv is None else argv
    output = sys.stdout if output_stream is None else output_stream
    try:
        if arguments == ["--self-test"]:
            response = {"ok": True, "result": self_test()}
        elif arguments:
            raise RequestError("Only --self-test is accepted as a command-line argument.")
        else:
            stream = sys.stdin.buffer if input_stream is None else input_stream
            response = handle_request(read_request(stream))
    except (Exception, SystemExit, KeyboardInterrupt) as error:
        response = {"ok": False, "error": _explanation(error)}
    # ASCII escaping makes the line valid UTF-8 even on legacy Windows consoles.
    output.write(json.dumps(response, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n")
    output.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
