"""Offline profile decoder checks using explicit synthetic payloads."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import scope_settings as settings


def fixture():
    """A synthetic coarse, visible CH1 with hidden CH2, not a live record."""
    data = bytearray(208)
    data[0] = 1
    data[1] = 9
    struct.pack_into("<h", data, 8, -4)
    data[20] = 2
    struct.pack_into("<h", data, 25, 29)
    data[160] = 17
    data[161] = 17
    data[205:208] = bytes((5, 5, 1))
    return data


class SettingsDecoderChecks(unittest.TestCase):
    def test_fixed_layout_covers_every_byte_once_and_keeps_all_field_names(self):
        self.assertEqual(len(settings.FIELD_SPECS), 119)
        self.assertEqual(len({name for name, _ in settings.FIELD_SPECS}), 119)
        self.assertEqual(sum(width for _, width in settings.FIELD_SPECS), 208)
        decoded = settings.decode_raw(bytes(range(208)))
        self.assertEqual(decoded["VERT-CH1-VB"], 1)
        self.assertEqual(decoded["VERT-CH2-DISP"], 10)
        self.assertEqual(decoded["TRIG-EDGE-SLOPE"], 59)
        self.assertEqual(decoded["HORIZ-TB"], 160)
        self.assertEqual(decoded["CONTROL-TYPE"], 205)
        self.assertEqual(decoded["CONTROL-MENUID"], 206)
        self.assertEqual(decoded["CONTROL-DISP-MENU"], 207)
        # Retain the firmware's spelling and asymmetric CH1/CH2 pulse widths.
        self.assertIn("ACQURIE-MODE", decoded)
        self.assertEqual(dict(settings.FIELD_SPECS)["TRIG-SWAP-CH1-PULSE-TIME"], 1)
        self.assertEqual(dict(settings.FIELD_SPECS)["TRIG-SWAP-CH2-PULSE-TIME"], 8)

    def test_signed_positions_and_full_unsigned_64_bit_values_are_preserved(self):
        payload = fixture()
        struct.pack_into("<h", payload, 8, -32768)
        struct.pack_into("<h", payload, 18, 32767)
        struct.pack_into("<h", payload, 25, -32536)
        struct.pack_into("<Q", payload, 27, (1 << 64) - 1)
        raw = settings.decode_raw(payload)
        self.assertEqual(raw["VERT-CH1-POS"], -32768)
        self.assertEqual(raw["VERT-CH2-POS"], 32767)
        self.assertEqual(raw["TRIG-VPOS"], -32536)
        self.assertEqual(raw["TRIG-FREQUENCY"], (1 << 64) - 1)

    def test_wrong_length_and_nonbinary_inputs_are_rejected(self):
        for payload in (b"", bytes(207), bytes(209), bytes(65536), "x" * 208, [0] * 208, None):
            with self.subTest(kind=type(payload).__name__), self.assertRaises(settings.SettingsError):
                settings.decode_raw(payload)
            with self.assertRaises(settings.SettingsError):
                settings.decode_settings(payload)

    def test_protocol_validation_is_exact_hash_not_layout_length_or_normalized_text(self):
        for payload in (b"", b"[TOTAL] 208\n[START]\n[END]\n", b"x" * 32769, "schema"):
            with self.assertRaises(settings.SettingsError):
                settings.validate_protocol(payload)
        # Exercise the acceptance branch with a synthetic digest, without
        # adding the vendor schema to tracked tests or mocking hashlib itself.
        sample = b"synthetic test schema\r\n"
        with mock.patch.object(settings, "PROFILE_SHA256", hashlib.sha256(sample).hexdigest()):
            valid = settings.validate_protocol(sample)
            self.assertTrue(valid["validated"])
            self.assertEqual(valid["total_bytes"], 208)
            self.assertEqual(valid["field_count"], 119)
            with self.assertRaises(settings.SettingsError):
                settings.validate_protocol(sample.replace(b"\r\n", b"\n"))
            with self.assertRaises(settings.SettingsError):
                settings.validate_protocol(sample + b" ")

    def test_confirmed_scales_positions_and_menu_decode_without_failing_hidden_channel(self):
        decoded = settings.decode_settings(fixture())
        state = decoded["state"]
        self.assertEqual(state["ch1.volts_per_div"], 1.0)
        self.assertEqual(state["ch1.position_div"], -0.16)
        self.assertEqual(state["ch1.probe"], 1)
        self.assertEqual(state["ch1.coupling"], "dc")
        self.assertTrue(state["ch1.enabled"])
        self.assertFalse(state["ch2.enabled"])
        self.assertNotIn("ch2.volts_per_div", state)
        self.assertIn("hidden channel", decoded["unknown_fields"]["ch2.volts_per_div"])
        self.assertEqual(state["horizontal.seconds_per_div"], .0008)
        self.assertEqual(state["control.menu_id"], 5)
        self.assertTrue(state["control.menu_visible"])
        self.assertEqual(state["trigger.slope"], "rising")
        self.assertEqual(state["trigger.level_volts"], 1.32)
        self.assertNotIn("validated", decoded)

    def test_voltage_scale_includes_known_probe_multiplier_and_omits_fine_mode(self):
        payload = fixture()
        payload[1] = 10
        payload[5] = 1
        self.assertEqual(settings.decode_settings(payload)["state"]["ch1.volts_per_div"], 20.0)
        for fine in (1, 255):
            payload[4] = fine
            result = settings.decode_settings(payload)
            self.assertNotIn("ch1.volts_per_div", result["state"])
            self.assertIn("ch1.volts_per_div", result["unknown_fields"])

    def test_unknown_enums_are_preserved_raw_and_never_defaulted(self):
        payload = fixture()
        for offset in (2, 5, 21, 22, 23, 24, 59, 162, 207):
            payload[offset] = 255
        decoded = settings.decode_settings(payload)
        self.assertEqual(decoded["raw_fields"]["VERT-CH1-COUP"], 255)
        self.assertEqual(decoded["raw_fields"]["TRIG-TYPE"], 255)
        for name in ("ch1.coupling", "ch1.probe", "ch1.volts_per_div", "trigger.type",
                     "trigger.source", "trigger.mode", "trigger.coupling", "trigger.slope",
                     "horizontal.window_enabled", "control.menu_visible"):
            self.assertNotIn(name, decoded["state"])
            self.assertIn(name, decoded["unknown_fields"])

    def test_timebase_bounds_and_lookup_are_explicit(self):
        self.assertEqual(set(settings.SECONDS_PER_DIV), set(range(1, 32)))
        self.assertEqual(settings.SECONDS_PER_DIV[1], 4e-9)
        self.assertEqual(settings.SECONDS_PER_DIV[17], 800e-6)
        self.assertEqual(settings.SECONDS_PER_DIV[18], 2e-3)
        self.assertEqual(settings.SECONDS_PER_DIV[31], 40.0)
        payload = fixture()
        for index in (0, 32, 255):
            payload[160] = index
            result = settings.decode_settings(payload)
            self.assertNotIn("horizontal.seconds_per_div", result["state"])
            self.assertIn("horizontal.seconds_per_div", result["unknown_fields"])

    def test_non_edge_or_hidden_source_does_not_claim_absolute_trigger_voltage(self):
        payload = fixture()
        payload[21] = 2
        payload[22] = 1
        struct.pack_into("<h", payload, 25, -32536)
        result = settings.decode_settings(payload)
        self.assertEqual(result["state"]["trigger.type"], "pulse")
        self.assertEqual(result["state"]["trigger.source"], "ch2")
        self.assertNotIn("trigger.level_volts", result["state"])
        self.assertNotIn("trigger.slope", result["state"])

    def test_level_accounts_for_channel_position_and_its_observed_relative_step(self):
        payload = fixture()
        self.assertEqual(settings.decode_settings(payload)["state"]["trigger.level_volts"], 1.32)
        struct.pack_into("<h", payload, 8, -3)
        struct.pack_into("<h", payload, 25, 30)
        self.assertEqual(settings.decode_settings(payload)["state"]["trigger.level_volts"], 1.32)
        struct.pack_into("<h", payload, 25, 31)
        self.assertEqual(settings.decode_settings(payload)["state"]["trigger.level_volts"], 1.36)
        payload[5] = 1
        self.assertEqual(settings.decode_settings(payload)["state"]["trigger.level_volts"], 13.6)

    def test_level_uses_only_the_active_channel_scale_and_position(self):
        payload = fixture()
        payload[10] = 1
        payload[11] = 10
        payload[15] = 1
        payload[22] = 1
        struct.pack_into("<h", payload, 18, 4)
        struct.pack_into("<h", payload, 25, -21)
        self.assertEqual(settings.decode_settings(payload)["state"]["trigger.level_volts"], -20.0)

    def test_level_omits_unknown_hidden_fine_and_external_source_dependencies(self):
        for offset, value in ((0, 0), (0, 255), (1, 0), (1, 255), (4, 1),
                              (4, 255), (5, 255), (21, 1), (21, 255),
                              (22, 1), (22, 2), (22, 3), (22, 4), (22, 255)):
            with self.subTest(offset=offset, value=value):
                payload = fixture()
                payload[offset] = value
                decoded = settings.decode_settings(payload)
                self.assertNotIn("trigger.level_volts", decoded["state"])
                self.assertIn("trigger.level_volts", decoded["unknown_fields"])

    def test_level_rejects_outside_central_coordinates_and_overflow_sentinels(self):
        for offset in (8, 25):
            for value in (-32768, -32536, -101, 101, 32767):
                with self.subTest(offset=offset, value=value):
                    payload = fixture()
                    struct.pack_into("<h", payload, offset, value)
                    decoded = settings.decode_settings(payload)
                    self.assertNotIn("trigger.level_volts", decoded["state"])
                    self.assertIn("central display", decoded["unknown_fields"]["trigger.level_volts"])
        for value in (-100, 100):
            payload = fixture()
            struct.pack_into("<h", payload, 25, value)
            self.assertIn("trigger.level_volts", settings.decode_settings(payload)["state"])


if __name__ == "__main__":
    unittest.main()
