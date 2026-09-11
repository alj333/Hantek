"""Independent setup-engine checks. The semantic instrument never opens USB."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import scope_settings
import scope_setup as setup


# These few instrument settings are specified independently of the planner.
# Decoder byte-layout tests belong to test_scope_settings, not this simulation.
BASE_SCALES = {7: 0.2, 8: 0.5, 9: 1.0, 10: 2.0, 11: 5.0, 12: 10.0}
TIMEBASES = {16: 0.0004, 17: 0.0008, 18: 0.002, 19: 0.004}
PROBES = (1, 10, 100, 1000)
COUPLINGS = ("dc", "ac", "gnd")


def baseline():
    state = {
        "horizontal.seconds_per_div": 0.0008,
        "horizontal.window_seconds_per_div": 0.0008,
        "horizontal.window_enabled": False,
        "trigger.type": "edge", "trigger.source": "ch1", "trigger.mode": "auto",
        "trigger.coupling": "dc", "trigger.slope": "rising", "trigger.level_volts": 0.0,
        "control.menu_id": 1, "control.menu_visible": True,
    }
    raw = {
        "HORIZ-TB": 17, "HORIZ-WIN-TB": 17, "TRIG-TYPE": 0, "TRIG-SRC": 0, "TRIG-MODE": 0,
        "TRIG-SWAP-CH1-MODE": 0, "TRIG-SWAP-CH2-MODE": 0,
        "TRIG-COUP": 0, "TRIG-EDGE-SLOPE": 0, "TRIG-VPOS": 0,
        "CONTROL-MENUID": 1, "CONTROL-DISP-MENU": 1, "CONTROL-TYPE": 0,
        "TRIG-STATE": 0, "TRIG-FREQUENCY": 0, "FIXTURE-UNRELATED": 73,
    }
    for channel in ("ch1", "ch2"):
        state.update({f"{channel}.enabled": True, f"{channel}.fine": False,
                      f"{channel}.volts_per_div": 1.0, f"{channel}.probe": 1,
                      f"{channel}.coupling": "dc", f"{channel}.position_div": 0.0})
        prefix = "VERT-" + channel.upper() + "-"
        raw.update({prefix + "VB": 9, prefix + "PROBE": 0,
                    prefix + "COUP": 0, prefix + "POS": 0})
    return {"profile": "dso5102p-208-v1", "profile_sha256": scope_settings.PROFILE_SHA256,
            "profile_validated": True, "frame_checksum_verified": True,
            "raw_fields": raw, "state": state, "unknown_fields": {}, "warnings": []}


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class Instrument:
    def __init__(self, *, snapshot=None, behavior="normal", fail_read=None, clock=None):
        self.snapshot = deepcopy(snapshot or baseline())
        self.behavior, self.fail_read, self.clock = behavior, fail_read, clock
        self.presses, self.events = [], []
        self.read_count = 0

    def journal(self, event):
        self.events.append(deepcopy(event))

    def read(self):
        self.read_count += 1
        if self.read_count == self.fail_read:
            raise OSError("Synthetic settings read failed; instrument state unknown")
        return deepcopy(self.snapshot)

    def press(self, control):
        # The durable event must exist before even attempting a gesture.
        if not self.events or self.events[-1].get("event") != "before_press" or self.events[-1].get("control") != control:
            raise AssertionError("Gesture attempted before its durable journal event")
        self.presses.append(control)
        if self.behavior == "send_error":
            raise OSError("Synthetic send attempted; result unknown")
        if self.behavior == "interrupt":
            raise KeyboardInterrupt("Synthetic operator interruption")
        if self.clock:
            self.clock.now += 2
        if self.behavior == "no_progress":
            return
        self.apply(control, reverse=self.behavior == "reverse")
        if self.behavior == "unrelated_drift":
            self.snapshot["raw_fields"]["FIXTURE-UNRELATED"] += 1
        elif self.behavior == "layout_drift":
            self.snapshot["raw_fields"]["UNEXPECTED-NEW-FIELD"] = 1
        elif self.behavior == "acquisition_change":
            self.snapshot["raw_fields"]["TRIG-STATE"] = 2
        elif self.behavior == "incorrect_mode_mirror" and control == "softkey-4":
            self.snapshot["raw_fields"]["TRIG-SWAP-CH2-MODE"] = 0

    def apply(self, control, *, reverse=False):
        raw, state = self.snapshot["raw_fields"], self.snapshot["state"]
        for channel in ("ch1", "ch2"):
            prefix = "VERT-" + channel.upper() + "-"
            if control in (channel + "-scale-plus", channel + "-scale-minus"):
                delta = 1 if control.endswith("plus") else -1
                raw[prefix + "VB"] += -delta if reverse else delta
                state[channel + ".volts_per_div"] = BASE_SCALES[raw[prefix + "VB"]] * state[channel + ".probe"]
                if state["trigger.source"] == channel:
                    volts = state[channel + ".volts_per_div"]
                    raw["TRIG-VPOS"] = raw[prefix + "POS"] + round(state["trigger.level_volts"] * 25 / volts)
                    state["trigger.level_volts"] = (raw["TRIG-VPOS"] - raw[prefix + "POS"]) * volts / 25
                return
            if control == channel + "-menu":
                menu = 1 if channel == "ch1" else 2
                # Pressing the visible current channel menu may disable it.
                if state["control.menu_id"] == menu and state["control.menu_visible"]:
                    state[channel + ".enabled"] = False
                else:
                    raw["CONTROL-MENUID"] = state["control.menu_id"] = menu
                    raw["CONTROL-DISP-MENU"] = 1
                    state["control.menu_visible"] = True
                return
            if control in (channel + "-position-plus", channel + "-position-minus"):
                delta = 1 if control.endswith("plus") else -1
                raw[prefix + "POS"] += delta
                state[channel + ".position_div"] = raw[prefix + "POS"] / 25
                if state["trigger.source"] == channel:
                    raw["TRIG-VPOS"] += delta
                return
        if control in ("timebase-plus", "timebase-minus"):
            delta = 1 if control.endswith("plus") else -1
            raw["HORIZ-TB"] += delta
            raw["HORIZ-WIN-TB"] += delta
            state["horizontal.seconds_per_div"] = TIMEBASES[raw["HORIZ-TB"]]
            state["horizontal.window_seconds_per_div"] = TIMEBASES[raw["HORIZ-WIN-TB"]]
            return
        if control in ("trigger-level-plus", "trigger-level-minus"):
            raw["TRIG-VPOS"] += 1 if control.endswith("plus") else -1
            source = state["trigger.source"]
            position = raw["VERT-" + source.upper() + "-POS"]
            state["trigger.level_volts"] = (raw["TRIG-VPOS"] - position) * state[source + ".volts_per_div"] / 25
            return
        if control == "trigger-menu":
            raw["CONTROL-MENUID"] = state["control.menu_id"] = 5
            raw["CONTROL-DISP-MENU"] = 1
            state["control.menu_visible"] = True
            return
        menu = state["control.menu_id"]
        if menu in (1, 2) and control in ("softkey-1", "softkey-4"):
            channel = "ch" + str(menu)
            prefix = "VERT-" + channel.upper() + "-"
            if control == "softkey-1":
                raw[prefix + "COUP"] = (raw[prefix + "COUP"] + 1) % len(COUPLINGS)
                state[channel + ".coupling"] = COUPLINGS[raw[prefix + "COUP"]]
            else:
                old_probe = state[channel + ".probe"]
                raw[prefix + "PROBE"] = (raw[prefix + "PROBE"] + 1) % len(PROBES)
                state[channel + ".probe"] = PROBES[raw[prefix + "PROBE"]]
                state[channel + ".volts_per_div"] = BASE_SCALES[raw[prefix + "VB"]] * state[channel + ".probe"]
                if state["trigger.source"] == channel:
                    state["trigger.level_volts"] *= state[channel + ".probe"] / old_probe
            return
        if menu == 5 and control == "softkey-4":
            raw["TRIG-MODE"] = 1 - raw["TRIG-MODE"]
            raw["TRIG-SWAP-CH1-MODE"] = raw["TRIG-SWAP-CH2-MODE"] = raw["TRIG-MODE"]
            state["trigger.mode"] = "normal" if raw["TRIG-MODE"] else "auto"
            return
        if menu == 5 and control == "softkey-2":
            sources = ("ch1", "ch2", "ext", "ext5", "acline")
            raw["TRIG-SRC"] = (raw["TRIG-SRC"] + 1) % len(sources)
            source = state["trigger.source"] = sources[raw["TRIG-SRC"]]
            if source in ("ch1", "ch2"):
                position = raw["VERT-" + source.upper() + "-POS"]
                state["trigger.level_volts"] = (raw["TRIG-VPOS"] - position) * state[source + ".volts_per_div"] / 25
            else:
                state.pop("trigger.level_volts", None)
            return
        raise AssertionError("Unexpected or unsupported test gesture: " + str(control))


class SetupEngineChecks(unittest.TestCase):
    def run_setup(self, target, instrument=None, **limits):
        instrument = instrument or Instrument()
        result = setup.configure(instrument, target, instrument.journal, **limits)
        return instrument, result

    def assert_aborted(self, instrument, target, **limits):
        with self.assertRaises(setup.SetupError) as raised:
            setup.configure(instrument, target, instrument.journal, **limits)
        self.assertIsInstance(raised.exception.result, dict)
        self.assertNotEqual(raised.exception.result["status"], "verified")
        return raised.exception.result

    def test_target_validation_rejects_unknown_fields_types_and_nonfinite_numbers(self):
        valid = {"schema_version": 1, "settings": {"ch1.volts_per_div": 2, "trigger.source": "CH1"}}
        self.assertEqual(setup.validate_target(valid), {"ch1.volts_per_div": 2.0, "trigger.source": "ch1"})
        malformed = [None, [], {}, {**valid, "raw_payload": "00"}, {**valid, "schema_version": True},
                     {**valid, "schema_version": 2}, {"schema_version": 1, "settings": {}},
                     {"schema_version": 1, "settings": {"ch1": {"coupling": "ac"}}}]
        for key, value in [("ch1.volts_per_div", True), ("ch1.volts_per_div", "2"),
                           ("ch1.volts_per_div", 3), ("ch1.probe", 2),
                           ("trigger.type", "pulse"), ("trigger.coupling", "unknown"),
                           ("command", "factory-reset"), ("ch1.position_div", float("nan")),
                           ("trigger.level_volts", float("inf")), ("trigger.level_volts", -float("inf"))]:
            malformed.append({"schema_version": 1, "settings": {key: value}})
        for document in malformed:
            with self.subTest(document=document), self.assertRaises(setup.SetupError):
                setup.validate_target(document)

    def test_matching_target_is_verified_without_any_gesture(self):
        device, result = self.run_setup({"ch1.volts_per_div": 1, "trigger.type": "edge"})
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["steps"], 0)
        self.assertEqual(device.presses, [])
        self.assertEqual(device.read_count, 1)
        self.assertEqual(device.events[-1]["event"], "verified")

    def test_single_scale_gesture_is_journalled_then_read_back_and_unrelated_fields_stay(self):
        original = baseline()
        device, result = self.run_setup({"ch1.volts_per_div": 2})
        self.assertEqual(result["status"], "verified")
        self.assertEqual(device.presses, ["ch1-scale-plus"])
        self.assertEqual(device.read_count, 2)
        self.assertEqual(device.snapshot["state"]["ch1.volts_per_div"], 2)
        self.assertEqual(device.snapshot["raw_fields"]["FIXTURE-UNRELATED"], original["raw_fields"]["FIXTURE-UNRELATED"])
        self.assertEqual(device.snapshot["state"]["trigger.mode"], original["state"]["trigger.mode"])
        self.assertEqual([event["event"] for event in device.events], ["begin", "read", "before_press", "read", "verified"])

    def test_visible_channel_menu_is_not_pressed_again_before_its_softkey(self):
        device, result = self.run_setup({"ch1.coupling": "ac"})
        self.assertEqual(result["status"], "verified")
        self.assertEqual(device.presses, ["softkey-1"])
        self.assertTrue(device.snapshot["state"]["ch1.enabled"])

    def test_trigger_menu_is_verified_before_sending_its_contextual_key(self):
        device, result = self.run_setup({"trigger.mode": "normal"})
        self.assertEqual(result["status"], "verified")
        self.assertEqual(device.presses, ["trigger-menu", "softkey-4"])
        self.assertEqual(device.read_count, 3)
        self.assertEqual(device.snapshot["raw_fields"]["TRIG-SWAP-CH1-MODE"], 1)
        self.assertEqual(device.snapshot["raw_fields"]["TRIG-SWAP-CH2-MODE"], 1)

    def test_trigger_mode_must_update_both_observed_mirrors_or_abort(self):
        device = Instrument(behavior="incorrect_mode_mirror")
        self.assert_aborted(device, {"trigger.mode": "normal"})
        self.assertEqual(device.presses, ["trigger-menu", "softkey-4"])
        self.assertEqual(device.read_count, 3)

    def test_probe_change_precedes_scale_and_final_displayed_scale_matches(self):
        device, result = self.run_setup({"ch1.probe": 10, "ch1.volts_per_div": 5})
        self.assertEqual(result["status"], "verified")
        self.assertEqual(device.presses, ["softkey-4", "ch1-scale-minus"])
        self.assertEqual(device.snapshot["state"]["ch1.probe"], 10)
        self.assertEqual(device.snapshot["state"]["ch1.volts_per_div"], 5)

    def test_probe_factor_changes_displayed_nonzero_level_without_changing_raw_position(self):
        snapshot = baseline()
        snapshot["raw_fields"].update({"VERT-CH1-POS": -4, "TRIG-VPOS": 29})
        snapshot["state"].update({"ch1.position_div": -.16, "trigger.level_volts": 1.32})
        device, result = self.run_setup({"ch1.probe": 10}, Instrument(snapshot=snapshot))
        self.assertEqual(result["status"], "verified")
        self.assertEqual(device.presses, ["softkey-4"])
        self.assertEqual(device.snapshot["state"]["ch1.volts_per_div"], 10)
        self.assertAlmostEqual(device.snapshot["state"]["trigger.level_volts"], 13.2)
        self.assertEqual(device.snapshot["raw_fields"]["TRIG-VPOS"], 29)
        self.assertEqual(device.snapshot["raw_fields"]["VERT-CH1-POS"], -4)

    def test_timebase_changes_main_and_matching_window_by_the_observed_single_step(self):
        device, result = self.run_setup({"horizontal.seconds_per_div": .002})
        self.assertEqual(result["status"], "verified")
        self.assertEqual(device.presses, ["timebase-plus"])
        self.assertEqual(device.snapshot["raw_fields"]["HORIZ-TB"], 18)
        self.assertEqual(device.snapshot["raw_fields"]["HORIZ-WIN-TB"], 18)

    def test_source_position_change_preserves_the_observed_absolute_trigger_level(self):
        snapshot = baseline()
        snapshot["raw_fields"].update({"VERT-CH1-POS": -4, "TRIG-VPOS": 29})
        snapshot["state"].update({"ch1.position_div": -.16, "trigger.level_volts": 1.32})
        device, result = self.run_setup({"ch1.position_div": -.12}, Instrument(snapshot=snapshot))
        self.assertEqual(result["status"], "verified")
        self.assertEqual(device.presses, ["ch1-position-plus"])
        self.assertEqual(device.snapshot["raw_fields"]["VERT-CH1-POS"], -3)
        self.assertEqual(device.snapshot["raw_fields"]["TRIG-VPOS"], 30)
        self.assertEqual(device.snapshot["state"]["trigger.level_volts"], 1.32)

    def test_absolute_trigger_level_uses_source_position_and_actual_displayed_scale(self):
        snapshot = baseline()
        snapshot["raw_fields"].update({"VERT-CH1-POS": -3, "TRIG-VPOS": 30})
        snapshot["state"].update({"ch1.position_div": -.12, "trigger.level_volts": 1.32})
        device, result = self.run_setup({"trigger.level_volts": 1.36}, Instrument(snapshot=snapshot))
        self.assertEqual(result["status"], "verified")
        self.assertEqual(device.presses, ["trigger-level-plus"])
        self.assertEqual(device.snapshot["raw_fields"]["TRIG-VPOS"], 31)
        self.assertEqual(device.snapshot["state"]["trigger.level_volts"], 1.36)

    def test_an_unrepresentable_later_target_rejects_before_changing_an_earlier_field(self):
        for target in ({"ch1.volts_per_div": 2, "ch2.position_div": .01},
                       {"ch1.volts_per_div": 2, "trigger.level_volts": .01}):
            with self.subTest(target=target):
                device = Instrument()
                with self.assertRaises(setup.SetupError):
                    setup.configure(device, target, device.journal)
                self.assertEqual(device.presses, [])

    def test_central_position_and_offset_trigger_bounds_reject_before_changes(self):
        device = Instrument()
        with self.assertRaises(setup.SetupError):
            setup.configure(device, {"ch1.position_div": 5}, device.journal)
        self.assertEqual(device.presses, [])
        snapshot = baseline()
        snapshot["raw_fields"].update({"VERT-CH1-POS": 25, "TRIG-VPOS": 25})
        snapshot["state"]["ch1.position_div"] = 1.0
        device = Instrument(snapshot=snapshot)
        self.assert_aborted(device, {"ch2.coupling": "ac", "trigger.level_volts": 3.2})
        self.assertEqual(device.presses, [])

    def test_preserved_trigger_would_leave_central_range_rejects_before_position_change(self):
        snapshot = baseline()
        snapshot["raw_fields"].update({"VERT-CH1-POS": 90, "TRIG-VPOS": 100})
        snapshot["state"].update({"ch1.position_div": 3.6, "trigger.level_volts": .4})
        device = Instrument(snapshot=snapshot)
        self.assert_aborted(device, {"ch1.position_div": 3.64})
        self.assertEqual(device.presses, [])

    def test_explicit_external_to_channel_source_converges_before_setting_absolute_level(self):
        snapshot = baseline()
        snapshot["raw_fields"]["TRIG-SRC"] = 2
        snapshot["state"]["trigger.source"] = "ext"
        del snapshot["state"]["trigger.level_volts"]
        device, result = self.run_setup({"trigger.source": "ch1", "trigger.level_volts": .08}, Instrument(snapshot=snapshot))
        self.assertEqual(result["status"], "verified")
        self.assertEqual(device.presses.count("softkey-2"), 3)
        self.assertEqual(device.presses.count("trigger-level-plus"), 2)
        self.assertEqual(device.snapshot["state"]["trigger.source"], "ch1")
        self.assertEqual(device.snapshot["state"]["trigger.level_volts"], .08)

    def test_unknown_active_source_threshold_rejects_all_prior_field_changes(self):
        snapshot = baseline()
        snapshot["raw_fields"]["TRIG-SRC"] = 1
        snapshot["state"]["trigger.source"] = "ch2"
        del snapshot["state"]["trigger.level_volts"]
        device = Instrument(snapshot=snapshot)
        self.assert_aborted(device, {"ch1.coupling": "ac", "ch2.volts_per_div": 2})
        self.assertEqual(device.presses, [])

    def test_acquisition_family_is_preserved_while_normal_active_states_may_change(self):
        device = Instrument(behavior="acquisition_change")
        self.assert_aborted(device, {"ch1.volts_per_div": 2})
        self.assertEqual(device.presses, ["ch1-scale-plus"])
        snapshot = baseline(); snapshot["raw_fields"]["TRIG-STATE"] = 1
        device, result = self.run_setup({"ch1.volts_per_div": 2}, Instrument(snapshot=snapshot, behavior="acquisition_change"))
        self.assertEqual(result["status"], "verified")
        self.assertEqual(device.snapshot["raw_fields"]["TRIG-STATE"], 2)

    def test_invalid_profile_or_unreliable_enum_aborts_before_any_press(self):
        snapshots = []
        snapshot = baseline(); snapshot["profile"] = "unknown-firmware"; snapshots.append(snapshot)
        snapshot = baseline(); snapshot["profile_sha256"] = "0" * 64; snapshots.append(snapshot)
        for marker in ("profile_validated", "frame_checksum_verified"):
            snapshot = baseline(); snapshot[marker] = False; snapshots.append(snapshot)
            snapshot = baseline(); del snapshot[marker]; snapshots.append(snapshot)
        snapshot = baseline(); del snapshot["state"]["ch1.coupling"]; snapshot["unknown_fields"]["ch1.coupling"] = "Unknown enum99"; snapshots.append(snapshot)
        for snapshot in snapshots:
            with self.subTest(profile=snapshot["profile"]):
                device = Instrument(snapshot=snapshot)
                self.assert_aborted(device, {"ch1.coupling": "ac"})
                self.assertEqual(device.presses, [])

    def test_invalid_baseline_dependencies_reject_before_any_changes(self):
        cases = [("ch1.enabled", False, {"ch1.coupling": "ac"}),
                 ("ch1.fine", True, {"ch1.volts_per_div": 2}),
                 ("horizontal.window_enabled", True, {"horizontal.seconds_per_div": .002}),
                 ("trigger.type", "video", {"trigger.mode": "normal"})]
        for key, value, target in cases:
            with self.subTest(key=key):
                snapshot = baseline(); snapshot["state"][key] = value
                device = Instrument(snapshot=snapshot)
                self.assert_aborted(device, target)
                self.assertEqual(device.presses, [])

    def test_no_progress_and_wrong_direction_stop_after_one_gesture(self):
        for behavior in ("no_progress", "reverse"):
            with self.subTest(behavior=behavior):
                device = Instrument(behavior=behavior)
                result = self.assert_aborted(device, {"ch1.volts_per_div": 2})
                self.assertEqual(device.presses, ["ch1-scale-plus"])
                self.assertEqual(result["steps"], 1)
                self.assertEqual(device.read_count, 2)

    def test_unrelated_field_or_layout_drift_cannot_be_reported_as_verified(self):
        for behavior in ("unrelated_drift", "layout_drift"):
            with self.subTest(behavior=behavior):
                device = Instrument(behavior=behavior)
                self.assert_aborted(device, {"ch1.volts_per_div": 2})
                self.assertEqual(device.presses, ["ch1-scale-plus"])

    def test_failed_send_is_never_retried_or_automatically_rolled_back(self):
        device = Instrument(behavior="send_error")
        result = self.assert_aborted(device, {"ch1.volts_per_div": 2})
        self.assertEqual(device.presses, ["ch1-scale-plus"])
        self.assertEqual(device.read_count, 1)
        self.assertEqual(result["steps"], 1)
        self.assertIn("unknown", result["error"])

    def test_failed_read_after_gesture_keeps_initial_and_attempt_without_retry(self):
        device = Instrument(fail_read=2)
        result = self.assert_aborted(device, {"ch1.volts_per_div": 2})
        self.assertEqual(device.presses, ["ch1-scale-plus"])
        self.assertEqual(device.read_count, 2)
        self.assertEqual(result["initial"]["state"]["ch1.volts_per_div"], 1)
        self.assertEqual(result["steps"], 1)

    def test_journal_failure_prevents_the_next_press(self):
        device = Instrument()
        def broken_journal(record):
            if record["event"] == "before_press":
                raise OSError("Synthetic journal disk full")
            device.journal(record)
        with self.assertRaises(setup.SetupError) as raised:
            setup.configure(device, {"ch1.volts_per_div": 2}, broken_journal)
        self.assertEqual(device.presses, [])
        self.assertEqual(raised.exception.result["steps"], 0)

    def test_interruption_preserves_partial_audit_and_never_repeats(self):
        device = Instrument(behavior="interrupt")
        try:
            setup.configure(device, {"ch1.volts_per_div": 2}, device.journal)
        except (setup.SetupError, KeyboardInterrupt):
            pass
        else:
            self.fail("Interruption must not become a verified result")
        self.assertEqual(device.presses, ["ch1-scale-plus"])
        self.assertEqual(device.read_count, 1)
        self.assertEqual(device.events[-1]["event"], "aborted")

    def test_step_and_time_budgets_stop_before_a_second_gesture(self):
        device = Instrument()
        result = self.assert_aborted(device, {"ch1.volts_per_div": 5}, max_steps=1)
        self.assertEqual(device.presses, ["ch1-scale-plus"])
        self.assertEqual(result["steps"], 1)
        clock = Clock()
        device = Instrument(clock=clock)
        self.assert_aborted(device, {"ch1.volts_per_div": 5}, clock=clock, timeout_seconds=1)
        self.assertEqual(device.presses, ["ch1-scale-plus"])


if __name__ == "__main__":
    unittest.main()
