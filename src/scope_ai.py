"""File-based AI setup entry points using the existing exclusive USB client."""
import datetime
import json
import os
from pathlib import Path
import time

import scope_settings
import scope_setup

MAX_TARGET_BYTES = 16384


def load_target(path):
    """Reject ambiguous JSON and oversized inputs before opening USB."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate setup key: " + key)
            result[key] = value
        return result

    def invalid_number(value):
        raise ValueError("Setup numbers must be finite: " + value)

    with Path(path).open("rb") as source:
        raw = source.read(MAX_TARGET_BYTES + 1)
    if len(raw) > MAX_TARGET_BYTES:
        raise ValueError("Setup file exceeds 16 KiB")
    document = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs,
                          parse_constant=invalid_number)
    return scope_setup.validate_target(document)


class SetupDriver:
    def __init__(self, client, device, log_dir, deadline):
        self.client, self.device = client, device
        self.log_dir, self.deadline = log_dir, deadline
        self.profile = None

    def initialize(self):
        expected = {"vid": "049F", "pid": "505A", "device_version_bcd": "2430"}
        if any(self.device.metadata.get(key) != value for key, value in expected.items()):
            raise ValueError("Numeric setup is restricted to the tested DSO5102P USB revision")
        evidence = self.client.read_protocol(self.device, self.log_dir, emit=False,
                                             overall_deadline=self.deadline)
        self.profile = scope_settings.validate_protocol(Path(evidence["raw_path"]).read_bytes())
        self.profile["evidence_path"] = evidence["log_path"]
        # The instrument needs time to leave its bulk-file reply handler before
        # another command on the same handle. Never resend a timed-out command.
        time.sleep(self.client.PANEL_SETTLE_SECONDS)
        self.client._check_transaction_deadline(self.deadline)
        return self.profile

    def read(self):
        if self.profile is None:
            raise ValueError("Read the instrument profile before interpreting settings")
        evidence = self.client.read_settings(self.device, self.log_dir, emit=False,
                                             overall_deadline=self.deadline)
        snapshot = scope_settings.decode_settings(bytes.fromhex(evidence["payload_hex"]))
        snapshot["profile_validated"] = True
        snapshot["frame_checksum_verified"] = True
        snapshot["evidence_path"] = evidence["log_path"]
        snapshot["settings_sha256"] = evidence["sha256"]
        # A settings reply can precede the firmware returning to its command
        # loop. An immediate following key was ignored on this unit. Pace the
        # next request instead of retrying an uncertain state-changing command.
        time.sleep(self.client.PANEL_SETTLE_SECONDS)
        self.client._check_transaction_deadline(self.deadline)
        return snapshot

    def press(self, control_id):
        result = self.client.panel_control(self.device, control_id, 1, self.log_dir,
                                            emit=False, overall_deadline=self.deadline)
        # Allow the display/settings handler to settle after the echo boundary.
        time.sleep(self.client.PANEL_SETTLE_SECONDS)
        self.client._check_transaction_deadline(self.deadline)
        return result


def run(client, device, args):
    """One final JSON record; all constituent operations retain their evidence."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = args.log_dir / (args.command + "-" + stamp)
    run_dir.mkdir(parents=True, exist_ok=False)
    result_path = run_dir / "result.json"
    journal_path = run_dir / "journal.jsonl"
    result = {"command": args.command, "status": "incomplete", "started_at_utc": stamp,
              "log_path": str(result_path), "journal_path": str(journal_path),
              "device": device.metadata, "settings_verified": False}
    client._write_operation_record(result_path, result, "x")
    deadline = time.monotonic() + 120
    driver = SetupDriver(client, device, run_dir / "operations", deadline)
    try:
        with journal_path.open("x", encoding="utf-8") as journal_file:
            def journal(record):
                journal_file.write(json.dumps(record, allow_nan=False) + "\n")
                journal_file.flush()
                os.fsync(journal_file.fileno())
            result["profile"] = driver.initialize()
            if args.command == "settings":
                result["snapshot"] = driver.read()
                journal({"event": "settings_read", "snapshot": result["snapshot"]})
                result.update(status="complete", instrument_settings_changed=False,
                              interpretation="Profile-specific readback; inspect warnings for unavailable fields.")
            else:
                result["target"] = args.target
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("Setup deadline expired during profile validation")
                result["setup"] = scope_setup.configure(driver, args.target, journal,
                                                        timeout_seconds=remaining)
                result.update(status="verified", settings_verified=True,
                              verification="Requested settings matched fresh instrument readback; not a measurement calibration.")
    except (Exception, KeyboardInterrupt) as error:
        result.update(status="aborted", error=str(error) or type(error).__name__)
        if hasattr(error, "result"):
            result["setup"] = error.result
        raise
    finally:
        try:
            client._write_operation_record(result_path, result)
        except (Exception, KeyboardInterrupt) as error:
            result.update(status="aborted", settings_verified=False,
                          audit_error="Could not finalize the operation record: " + (str(error) or type(error).__name__))
            raise
        finally:
            print(json.dumps(result, indent=2, allow_nan=False))
    return result
