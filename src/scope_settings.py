"""Decode the pinned 208-byte DSO5102P profile without accessing hardware.

Field names and widths are protocol facts from the owner's hash-verified
/protocol.inf, also published by the exact-model community implementation.
No vendor schema file or external implementation code is shipped here.
Call validate_protocol on the actual instrument schema before trusting this
profile for a connection; a 208-byte response alone does not identify firmware.
"""
import hashlib


PROFILE = "dso5102p-208-v1"
PROFILE_SHA256 = "fbd58fa396f2e3922fcd8b9000ba505eb627ee162956937ce1a1f8b07169995d"
SETTINGS_BYTES = 208
# Only interpret trigger/channel display coordinates inside the central eight
# divisions. This conservative software limit is not the instrument's full range.
CENTRAL_POSITION_TICKS = 100

FIELD_SPECS = (
    ("VERT-CH1-DISP", 1), ("VERT-CH1-VB", 1), ("VERT-CH1-COUP", 1),
    ("VERT-CH1-20MHZ", 1), ("VERT-CH1-FINE", 1), ("VERT-CH1-PROBE", 1),
    ("VERT-CH1-RPHASE", 1), ("VERT-CH1-CNT-FINE", 1), ("VERT-CH1-POS", 2),
    ("VERT-CH2-DISP", 1), ("VERT-CH2-VB", 1), ("VERT-CH2-COUP", 1),
    ("VERT-CH2-20MHZ", 1), ("VERT-CH2-FINE", 1), ("VERT-CH2-PROBE", 1),
    ("VERT-CH2-RPHASE", 1), ("VERT-CH2-CNT-FINE", 1), ("VERT-CH2-POS", 2),
    ("TRIG-STATE", 1), ("TRIG-TYPE", 1), ("TRIG-SRC", 1), ("TRIG-MODE", 1),
    ("TRIG-COUP", 1), ("TRIG-VPOS", 2), ("TRIG-FREQUENCY", 8),
    ("TRIG-HOLDTIME-MIN", 8), ("TRIG-HOLDTIME-MAX", 8), ("TRIG-HOLDTIME", 8),
    ("TRIG-EDGE-SLOPE", 1), ("TRIG-VIDEO-NEG", 1), ("TRIG-VIDEO-PAL", 1),
    ("TRIG-VIDEO-SYN", 1), ("TRIG-VIDEO-LINE", 2), ("TRIG-PULSE-NEG", 1),
    ("TRIG-PULSE-WHEN", 1), ("TRIG-PULSE-TIME", 8), ("TRIG-SLOPE-SET", 1),
    ("TRIG-SLOPE-WIN", 1), ("TRIG-SLOPE-WHEN", 1), ("TRIG-SLOPE-V1", 2),
    ("TRIG-SLOPE-V2", 2), ("TRIG-SLOPE-TIME", 8), ("TRIG-SWAP-CH1-TYPE", 1),
    ("TRIG-SWAP-CH1-MODE", 1), ("TRIG-SWAP-CH1-COUP", 1),
    ("TRIG-SWAP-CH1-EDGE-SLOPE", 1), ("TRIG-SWAP-CH1-VIDEO-NEG", 1),
    ("TRIG-SWAP-CH1-VIDEO-PAL", 1), ("TRIG-SWAP-CH1-VIDEO-SYN", 1),
    ("TRIG-SWAP-CH1-VIDEO-LINE", 2), ("TRIG-SWAP-CH1-PULSE-NEG", 1),
    ("TRIG-SWAP-CH1-PULSE-WHEN", 1), ("TRIG-SWAP-CH1-PULSE-TIME", 1),
    ("TRIG-SWAP-CH1-SLOPE-SET", 1), ("TRIG-SWAP-CH1-SLOPE-WIN", 1),
    ("TRIG-SWAP-CH1-SLOPE-WHEN", 1), ("TRIG-SWAP-CH1-SLOPE-V1", 2),
    ("TRIG-SWAP-CH1-SLOPE-V2", 2), ("TRIG-SWAP-CH1-SLOPE-TIME", 8),
    ("TRIG-SWAP-CH2-TYPE", 1), ("TRIG-SWAP-CH2-MODE", 1),
    ("TRIG-SWAP-CH2-COUP", 1), ("TRIG-SWAP-CH2-EDGE-SLOPE", 1),
    ("TRIG-SWAP-CH2-VIDEO-NEG", 1), ("TRIG-SWAP-CH2-VIDEO-PAL", 1),
    ("TRIG-SWAP-CH2-VIDEO-SYN", 1), ("TRIG-SWAP-CH2-VIDEO-LINE", 2),
    ("TRIG-SWAP-CH2-PULSE-NEG", 1), ("TRIG-SWAP-CH2-PULSE-WHEN", 1),
    ("TRIG-SWAP-CH2-PULSE-TIME", 8), ("TRIG-SWAP-CH2-SLOPE-SET", 1),
    ("TRIG-SWAP-CH2-SLOPE-WIN", 1), ("TRIG-SWAP-CH2-SLOPE-WHEN", 1),
    ("TRIG-SWAP-CH2-SLOPE-V1", 2), ("TRIG-SWAP-CH2-SLOPE-V2", 2),
    ("TRIG-SWAP-CH2-SLOPE-TIME", 8), ("TRIG-OVERTIME-NEG", 1),
    ("TRIG-OVERTIME-TIME", 8), ("HORIZ-TB", 1), ("HORIZ-WIN-TB", 1),
    ("HORIZ-WIN-STATE", 1), ("HORIZ-TRIGTIME", 8), ("MATH-DISP", 1),
    ("MATH-MODE", 1), ("MATH-FFT-SRC", 1), ("MATH-FFT-WIN", 1),
    ("MATH-FFT-FACTOR", 1), ("MATH-FFT-DB", 1), ("DISPLAY-MODE", 1),
    ("DISPLAY-PERSIST", 1), ("DISPLAY-FORMAT", 1), ("DISPLAY-CONTRAST", 1),
    ("DISPLAY-MAXCONTRAST", 1), ("DISPLAY-GRID-KIND", 1),
    ("DISPLAY-GRID-BRIGHT", 1), ("DISPLAY-MAXGRID-BRIGHT", 1),
    ("ACQURIE-MODE", 1), ("ACQURIE-AVG-CNT", 1), ("ACQURIE-TYPE", 1),
    ("ACQURIE-STORE-DEPTH", 1), ("MEASURE-ITEM1-SRC", 1), ("MEASURE-ITEM1", 1),
    ("MEASURE-ITEM2-SRC", 1), ("MEASURE-ITEM2", 1), ("MEASURE-ITEM3-SRC", 1),
    ("MEASURE-ITEM3", 1), ("MEASURE-ITEM4-SRC", 1), ("MEASURE-ITEM4", 1),
    ("MEASURE-ITEM5-SRC", 1), ("MEASURE-ITEM5", 1), ("MEASURE-ITEM6-SRC", 1),
    ("MEASURE-ITEM6", 1), ("MEASURE-ITEM7-SRC", 1), ("MEASURE-ITEM7", 1),
    ("MEASURE-ITEM8-SRC", 1), ("MEASURE-ITEM8", 1), ("CONTROL-TYPE", 1),
    ("CONTROL-MENUID", 1), ("CONTROL-DISP-MENU", 1),
)

# Base input volts/div. The instrument's displayed scale includes its selected
# probe multiplier. VB 9 -> 1 V and VB 10 -> 2 V were checked on this unit.
# Index 0 is intentionally unsupported, including when reported by hidden CH2.
VOLTS_PER_DIV = {1: .002, 2: .005, 3: .01, 4: .02, 5: .05, 6: .1,
                 7: .2, 8: .5, 9: 1.0, 10: 2.0, 11: 5.0, 12: 10.0}
# Firmware table: 2/4/8 ns by decades. This model's accepted indexes are 1..31;
# index 17 -> 800 us and the adjacent displayed 2 ms step were observed.
SECONDS_PER_DIV = {index: float("%se%s" % ((2, 4, 8)[index % 3], index // 3 - 9))
                   for index in range(1, 32)}
PROBE_FACTORS = {0: 1, 1: 10, 2: 100, 3: 1000}
ENUMS = {
    "ch1.coupling": {0: "dc", 1: "ac", 2: "gnd"},
    "ch2.coupling": {0: "dc", 1: "ac", 2: "gnd"},
    "ch1.probe": dict(PROBE_FACTORS), "ch2.probe": dict(PROBE_FACTORS),
    "trigger.type": {0: "edge", 1: "video", 2: "pulse", 3: "slope", 4: "overtime", 5: "alternate"},
    "trigger.source": {0: "ch1", 1: "ch2", 2: "ext", 3: "ext5", 4: "acline"},
    "trigger.mode": {0: "auto", 1: "normal"},
    "trigger.coupling": {0: "dc", 1: "ac", 2: "noise-reject", 3: "hf-reject", 4: "lf-reject"},
    "trigger.slope": {0: "rising", 1: "falling"},
    "trigger.state": {0: "stop", 1: "ready", 2: "auto", 3: "triggered", 4: "scan", 5: "astop", 6: "armed"},
}


class SettingsError(ValueError):
    """The schema, data length or type cannot be decoded by this profile."""


def _bytes(value, description):
    if not isinstance(value, (bytes, bytearray)):
        raise SettingsError(description + " must be binary bytes")
    return bytes(value)


def validate_protocol(data):
    """Validate the exact instrument schema bytes, without normalizing them."""
    raw = _bytes(data, "Protocol schema")
    if len(raw) > 32768 or hashlib.sha256(raw).hexdigest() != PROFILE_SHA256:
        raise SettingsError("The instrument protocol schema does not match the supported DSO5102P profile")
    return {"profile": PROFILE, "profile_sha256": PROFILE_SHA256,
            "total_bytes": SETTINGS_BYTES, "field_count": len(FIELD_SPECS), "validated": True}


def decode_raw(data):
    """Return every schema field as an integer, preserving unsupported values.

    One-byte fields are unsigned; two-byte fields use the source decoder's
    signed representation; eight-byte fields preserve unsigned 64-bit values.
    Raw integers do not claim physical units or a validated enumeration.
    """
    raw = _bytes(data, "Settings payload")
    if len(raw) != SETTINGS_BYTES:
        raise SettingsError("Expected exactly 208 SYSData bytes; got %d" % len(raw))
    result, offset = {}, 0
    for name, width in FIELD_SPECS:
        result[name] = int.from_bytes(raw[offset:offset + width], "little", signed=width == 2)
        offset += width
    if offset != SETTINGS_BYTES or len(result) != 119:
        raise SettingsError("The internal settings layout is inconsistent")
    return result


def decode_settings(data):
    """Decode supported state, omitting unknown/inactive SI values explicitly.

    The returned profile hash identifies the decoder, not proof that the caller
    fetched this schema from the current instrument. Validate that separately.
    """
    raw = decode_raw(data)
    state, unknown, warnings = {}, {}, []

    def unavailable(key, reason):
        unknown[key] = reason
        warnings.append(key + ": " + reason)

    def enum(key, field, values=None):
        table = ENUMS[key] if values is None else values
        value = raw[field]
        if value not in table:
            unavailable(key, "Unrecognized %s value %d" % (field, value))
            return None
        state[key] = table[value]
        return state[key]

    for number in (1, 2):
        channel = "ch%d" % number
        prefix = "VERT-CH%d-" % number
        enabled = enum(channel + ".enabled", prefix + "DISP", {0: False, 1: True})
        fine = enum(channel + ".fine", prefix + "FINE", {0: False, 1: True})
        enum(channel + ".inverted", prefix + "RPHASE", {0: False, 1: True})
        enum(channel + ".bandwidth_limited", prefix + "20MHZ", {0: False, 1: True})
        enum(channel + ".coupling", prefix + "COUP")
        probe = enum(channel + ".probe", prefix + "PROBE")
        state[channel + ".position_div"] = raw[prefix + "POS"] / 25.0
        index = raw[prefix + "VB"]
        key = channel + ".volts_per_div"
        if index not in VOLTS_PER_DIV:
            qualifier = "hidden channel; " if enabled is False else ""
            unavailable(key, "%sunsupported range index %d" % (qualifier, index))
        elif fine is not False:
            unavailable(key, "Coarse scale cannot be inferred while fine mode is enabled or unknown")
        elif probe is None:
            unavailable(key, "A recognized probe multiplier is required")
        else:
            state[key] = VOLTS_PER_DIV[index] * probe

    enum("horizontal.window_enabled", "HORIZ-WIN-STATE", {0: False, 1: True})
    for key, field in (("horizontal.seconds_per_div", "HORIZ-TB"),
                       ("horizontal.window_seconds_per_div", "HORIZ-WIN-TB")):
        index = raw[field]
        if index in SECONDS_PER_DIV:
            state[key] = SECONDS_PER_DIV[index]
        else:
            unavailable(key, "Unsupported timebase index %d" % index)

    trigger_type = enum("trigger.type", "TRIG-TYPE")
    trigger_source = enum("trigger.source", "TRIG-SRC")
    enum("trigger.mode", "TRIG-MODE")
    enum("trigger.coupling", "TRIG-COUP")
    enum("trigger.state", "TRIG-STATE")
    if trigger_type == "edge":
        enum("trigger.slope", "TRIG-EDGE-SLOPE")
    else:
        unavailable("trigger.slope", "Edge slope is not an active setting outside Edge triggering")
    level_key = "trigger.level_volts"
    if trigger_type != "edge":
        unavailable(level_key, "Absolute voltage is supported only for Edge triggering")
    elif trigger_source not in ("ch1", "ch2"):
        unavailable(level_key, "Absolute voltage requires a CH1 or CH2 trigger source")
    elif state.get(trigger_source + ".enabled") is not True:
        unavailable(level_key, "The trigger source channel must be visibly enabled")
    elif trigger_source + ".volts_per_div" not in state:
        unavailable(level_key, "The trigger source needs a recognized coarse scale and probe multiplier")
    else:
        source_position = raw["VERT-" + trigger_source.upper() + "-POS"]
        trigger_position = raw["TRIG-VPOS"]
        if any(abs(value) > CENTRAL_POSITION_TICKS for value in (source_position, trigger_position)):
            unavailable(level_key, "Trigger and source positions must be within the supported central display range")
        else:
            # Screen/readback checks: POS -4, VPOS 29 -> 1.32 V at 1 V/div;
            # POS -3, VPOS 30 preserves it; VPOS 31 then reads 1.36 V.
            # This reports the displayed threshold, not calibrated accuracy.
            state[level_key] = ((trigger_position - source_position) *
                                state[trigger_source + ".volts_per_div"] / 25.0)
    state["control.menu_id"] = raw["CONTROL-MENUID"]
    enum("control.menu_visible", "CONTROL-DISP-MENU", {0: False, 1: True})

    return {"profile": PROFILE, "profile_sha256": PROFILE_SHA256,
            "raw_fields": raw, "state": state, "unknown_fields": unknown,
            "warnings": warnings}
