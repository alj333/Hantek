"""Bounded settings convergence through named ordinary front-panel gestures.

This module performs no USB access or file I/O. The caller supplies one exclusive,
profile-validated driver and a durable journal. Every gesture is preceded by a
journal record and followed by a fresh settings read. Failure never causes a
retry, rollback, acquisition action, or a guessed numeric setting.
"""

from copy import deepcopy
import math
import time

import scope_settings


PROFILE = "dso5102p-208-v1"
MAX_STEPS = 80
MAX_SECONDS = 120
CHANNEL_KEYS = ("probe", "volts_per_div", "position_div", "coupling")
TRIGGER_KEYS = ("type", "source", "mode", "slope", "coupling", "level_volts")
SETTING_ORDER = tuple(
    [f"{channel}.{key}" for channel in ("ch1", "ch2") for key in CHANNEL_KEYS]
    + ["horizontal.seconds_per_div"]
    + [f"trigger.{key}" for key in TRIGGER_KEYS]
)
ENUM_VALUES = {
    "ch1.coupling": ("dc", "ac", "gnd"),
    "ch2.coupling": ("dc", "ac", "gnd"),
    "trigger.type": ("edge",),
    "trigger.source": ("ch1", "ch2", "ext", "ext5", "acline"),
    "trigger.mode": ("auto", "normal"),
    "trigger.slope": ("rising", "falling"),
    "trigger.coupling": ("dc", "ac", "noise-reject", "hf-reject", "lf-reject"),
}
MENU_FIELDS = frozenset(("CONTROL-TYPE", "CONTROL-MENUID", "CONTROL-DISP-MENU"))
DYNAMIC_FIELDS = frozenset(("TRIG-STATE", "TRIG-FREQUENCY"))


class SetupError(ValueError):
    """A rejected or unconfirmed setup; result preserves any partial progress."""

    def __init__(self, message, result=None):
        super().__init__(message)
        self.result = result


def _number(value, name):
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise SetupError(f"{name} must be a finite number, not a boolean")
    return float(value)


def _equal(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-15)
    return type(left) is type(right) and left == right


def _member(value, choices, name):
    for choice in choices:
        if _equal(value, choice):
            return choice
    raise SetupError(f"Unsupported {name}: {value!r}; use an exact supported value")


def validate_target(document):
    """Validate the versioned public document and return canonical flat settings."""
    if type(document) is not dict or set(document) != {"schema_version", "settings"}:
        raise SetupError("Target must contain only schema_version and settings")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise SetupError("Only schema_version 1 is supported")
    settings = document["settings"]
    if type(settings) is not dict or not settings or len(settings) > len(SETTING_ORDER):
        raise SetupError("settings must be a non-empty flat object of supported settings")
    result = {}
    for key, value in settings.items():
        if not isinstance(key, str) or key not in SETTING_ORDER:
            raise SetupError(f"Unsupported setting: {key!r}")
        if key in ENUM_VALUES:
            if not isinstance(value, str):
                raise SetupError(f"{key} must be a supported string value")
            result[key] = _member(value.strip().lower(), ENUM_VALUES[key], key)
        else:
            numeric = _number(value, key)
            if key.endswith(".probe"):
                result[key] = _member(numeric, (1, 10, 100, 1000), key)
            elif key.endswith(".volts_per_div"):
                choices = sorted({base * probe for base in scope_settings.VOLTS_PER_DIV.values()
                                  for probe in (1, 10, 100, 1000)})
                result[key] = _member(numeric, choices, key)
            elif key == "horizontal.seconds_per_div":
                result[key] = _member(numeric, scope_settings.SECONDS_PER_DIV.values(), key)
            elif key.endswith(".position_div"):
                _central(numeric * 25, key + " in 0.04-division increments")
                result[key] = numeric
            else:
                result[key] = numeric
    return {key: result[key] for key in SETTING_ORDER if key in result}


def capabilities():
    """Offline accepted targets; runtime prerequisites still apply to every setup."""
    settings = {}
    for key in SETTING_ORDER:
        if key in ENUM_VALUES:
            settings[key] = {"values": list(ENUM_VALUES[key])}
        elif key.endswith(".probe"):
            settings[key] = {"values": [1, 10, 100, 1000]}
        elif key.endswith(".volts_per_div"):
            settings[key] = {"base_values": list(scope_settings.VOLTS_PER_DIV.values()),
                             "unit": "V/div", "probe_factor_applies": True}
        elif key == "horizontal.seconds_per_div":
            settings[key] = {"values": list(scope_settings.SECONDS_PER_DIV.values()), "unit": "s/div"}
        elif key.endswith(".position_div"):
            settings[key] = {"unit": "div", "increment": 0.04, "minimum": -4, "maximum": 4}
        else:
            settings[key] = {"unit": "V", "quantization": "Exact source V/div divided by 25",
                             "bound": "±4 source divisions and central raw trigger position"}
    return {"schema_version": 1, "profile": PROFILE,
            "profile_sha256": scope_settings.PROFILE_SHA256, "settings": settings,
            "limits": {"max_steps": MAX_STEPS, "timeout_seconds": MAX_SECONDS},
            "prerequisites": ["An enabled channel for channel settings",
                              "Coarse vertical scale and main horizontal timebase",
                              "An existing Edge trigger for trigger changes",
                              "A verified readback after every single gesture"],
            "failure_behavior": "Abort without retries or rollback; partial changes remain possible"}


def _snapshot(value):
    if type(value) is not dict or value.get("profile") != PROFILE or \
            value.get("profile_sha256") != scope_settings.PROFILE_SHA256 or \
            value.get("profile_validated") is not True or value.get("frame_checksum_verified") is not True:
        raise SetupError("Settings readback does not match the validated instrument profile")
    raw, state = value.get("raw_fields"), value.get("state")
    if type(raw) is not dict or not raw or type(state) is not dict:
        raise SetupError("Settings readback is missing raw fields or decoded state")
    if any(not isinstance(key, str) or type(number) is not int for key, number in raw.items()):
        raise SetupError("Raw settings fields must contain named integer values")
    return deepcopy(value)


def _state(snapshot, key):
    if key not in snapshot["state"]:
        raise SetupError(f"Readback cannot reliably decode {key}")
    return snapshot["state"][key]


def _raw(snapshot, key):
    if key not in snapshot["raw_fields"]:
        raise SetupError(f"Readback is missing required raw field {key}")
    return snapshot["raw_fields"][key]


def _guard(before, after, allowed):
    left, right = before["raw_fields"], after["raw_fields"]
    if set(left) != set(right):
        raise SetupError("Settings field layout changed during configuration")
    changed = sorted(key for key in left if left[key] != right[key] and
                     key not in allowed and key not in MENU_FIELDS and key not in DYNAMIC_FIELDS)
    if changed:
        raise SetupError("Unrelated settings changed: " + ", ".join(changed))
    if _acquisition_family(before) != _acquisition_family(after):
        raise SetupError("Acquisition changed between stopped and active during configuration")


def _acquisition_family(snapshot):
    value = _raw(snapshot, "TRIG-STATE")
    if value in (0, 5):
        return "stopped"
    if value in (1, 2, 3, 4, 6):
        return "active"
    raise SetupError("Acquisition state is outside the supported settings enumeration")


def _preflight(snapshot, target):
    """Reject unsupported dependencies before the first state-changing request."""
    _acquisition_family(snapshot)
    for key in target:
        # A requested source change may pass external sources whose absolute
        # threshold is deliberately not decoded. Level is applied only after
        # the requested, enabled channel source has been reached.
        changing_source = key == "trigger.level_volts" and "trigger.source" in target and \
            _state(snapshot, "trigger.source") != target["trigger.source"]
        if not changing_source:
            _state(snapshot, key)
        if key.startswith(("ch1.", "ch2.")):
            channel = key.split(".")[0]
            if _state(snapshot, channel + ".enabled") is not True:
                raise SetupError(f"{channel.upper()} must already be enabled")
            if key.endswith(".volts_per_div") and _state(snapshot, channel + ".fine") is not False:
                raise SetupError(f"{channel.upper()} requires coarse scale; fine adjustment is active or unknown")
            if key.endswith(".volts_per_div"):
                probe = target.get(channel + ".probe", _state(snapshot, channel + ".probe"))
                _member(target[key] / probe, scope_settings.VOLTS_PER_DIV.values(), key + " at the selected probe factor")
        if key.startswith("trigger.") and _state(snapshot, "trigger.type") != "edge":
            raise SetupError("Trigger configuration currently requires an existing Edge trigger")
        if key == "horizontal.seconds_per_div" and _state(snapshot, "horizontal.window_enabled") is not False:
            raise SetupError("Timebase configuration requires the main timebase; window mode is active or unknown")
        if key == "horizontal.seconds_per_div" and _raw(snapshot, "HORIZ-TB") != _raw(snapshot, "HORIZ-WIN-TB"):
            raise SetupError("Timebase configuration currently requires matching main and window indices")
    for channel in ("ch1", "ch2"):
        dependent = [channel + "." + suffix for suffix in ("probe", "volts_per_div", "position_div")]
        if not any(key in target and not _equal(_state(snapshot, key), target[key]) for key in dependent):
            continue
        if _state(snapshot, "trigger.source") != channel:
            continue
        # These source-channel gestures preserve the input threshold, subject
        # to one new display quantum. Require that dependency before any write,
        # including before unrelated earlier settings in the requested target.
        level = _number(_state(snapshot, "trigger.level_volts"), "trigger.level_volts")
        probe = _number(_state(snapshot, channel + ".probe"), channel + ".probe")
        final_probe = target.get(channel + ".probe", probe)
        volts = target.get(channel + ".volts_per_div", _state(snapshot, channel + ".volts_per_div") * final_probe / probe)
        position = target.get(channel + ".position_div", _state(snapshot, channel + ".position_div"))
        preserved_level = level * final_probe / probe
        future_ticks = preserved_level * 25 / volts + position * 25
        if not math.isfinite(future_ticks) or abs(future_ticks) > scope_settings.CENTRAL_POSITION_TICKS + 1e-9:
            raise SetupError("Source-channel adjustment would move the preserved trigger outside the central display bound")
    if "trigger.level_volts" in target:
        source = target.get("trigger.source", _state(snapshot, "trigger.source"))
        if source not in ("ch1", "ch2") or _state(snapshot, source + ".enabled") is not True:
            raise SetupError("Absolute trigger level requires an enabled CH1 or CH2 source")
        if _state(snapshot, source + ".fine") is not False:
            raise SetupError("Absolute trigger level requires a coarse source-channel scale")
        probe = _state(snapshot, source + ".probe")
        final_probe = target.get(source + ".probe", probe)
        volts = target.get(source + ".volts_per_div", _state(snapshot, source + ".volts_per_div") * final_probe / probe)
        position = target.get(source + ".position_div", _state(snapshot, source + ".position_div"))
        if abs(target["trigger.level_volts"] / volts) > 4 + 1e-9:
            raise SetupError("Absolute trigger level is bounded to ±4 source-channel divisions")
        _central(target["trigger.level_volts"] * 25 / volts + position * 25,
                 "trigger.level_volts at the requested source scale and position")


def _integer(value, name):
    number = _number(value, name)
    nearest = round(number)
    if not _equal(number, nearest):
        raise SetupError(f"{name} is not exactly representable; no rounding will be applied")
    if not -32768 <= nearest <= 32767:
        raise SetupError(f"{name} exceeds the signed settings field")
    return nearest


def _central(value, name):
    integer = _integer(value, name)
    if abs(integer) > scope_settings.CENTRAL_POSITION_TICKS:
        raise SetupError(f"{name} must stay within the supported central ±4 divisions")
    return integer


def _enum_map(key):
    values = scope_settings.ENUMS.get(key)
    if not isinstance(values, dict) or not values:
        raise SetupError(f"Validated enumeration is unavailable for {key}")
    return values


def _menu_plan(snapshot, channel):
    menu, control = {"ch1": (1, "ch1-menu"), "ch2": (2, "ch2-menu"),
                     "trigger": (5, "trigger-menu")}[channel]
    current = _state(snapshot, "control.menu_id")
    visible = _state(snapshot, "control.menu_visible")
    if type(current) is not int or type(visible) is not bool:
        raise SetupError("Menu context is not reliable")
    if current == menu and visible:
        return None
    if current == menu and channel in ("ch1", "ch2"):
        raise SetupError("The selected channel menu is hidden; inspect the scope before reopening it")

    def verify(before, after):
        if _state(after, "control.menu_id") != menu or _state(after, "control.menu_visible") is not True:
            raise SetupError(f"Opening {channel} did not produce the expected visible menu")
        if _raw(after, "CONTROL-MENUID") != menu or _raw(after, "CONTROL-DISP-MENU") != 1:
            raise SetupError("Menu readback disagrees with its raw settings fields")
    return control, frozenset(), verify


def _trigger_dependency(snapshot, channel, *, probe_change=False):
    """Guard absolute level when a source-channel gesture quantizes its position."""
    if _state(snapshot, "trigger.source") != channel:
        return frozenset(), None
    old_level = _number(_state(snapshot, "trigger.level_volts"), "trigger.level_volts")
    old_probe = _number(_state(snapshot, channel + ".probe"), channel + ".probe") if probe_change else 1

    def verify(after):
        if _state(after, "trigger.source") != channel:
            raise SetupError("Trigger source changed during a source-channel adjustment")
        new_level = _number(_state(after, "trigger.level_volts"), "trigger.level_volts")
        quantum = _number(_state(after, channel + ".volts_per_div"), channel + ".volts_per_div") / 25
        new_probe = _number(_state(after, channel + ".probe"), channel + ".probe") if probe_change else 1
        if old_probe <= 0 or new_probe <= 0 or quantum <= 0 or \
                abs(new_level / new_probe - old_level / old_probe) > quantum / new_probe + 1e-12:
            raise SetupError("Source-channel adjustment changed trigger level beyond one new quantization step")
    return frozenset(("TRIG-VPOS",)), verify


def _value_plan(snapshot, key, raw_key, expected_raw, expected_value, control, *, dependency_channel=None,
                additional_fields=frozenset(), expected_additional=None):
    additional, verify_dependency = _trigger_dependency(snapshot, dependency_channel, probe_change=key.endswith(".probe")) \
        if dependency_channel is not None else (frozenset(), None)

    def verify(before, after):
        if _raw(after, raw_key) != expected_raw:
            raise SetupError(f"{control} did not make the expected single step in {raw_key}")
        if not _equal(_state(after, key), expected_value):
            raise SetupError(f"{key} readback does not match the expected step")
        for field, expected in (expected_additional or {}).items():
            if _raw(after, field) != expected:
                raise SetupError(f"{control} produced an unexpected dependent value in {field}")
        if verify_dependency is not None:
            verify_dependency(after)
    return control, frozenset((raw_key,)) | additional | additional_fields, verify


def _next_action(snapshot, key, target, complete_target):
    """Plan only the next single gesture from the just-read state and raw fields."""
    if key.startswith(("ch1.", "ch2.")):
        channel, setting = key.split(".")
        prefix = "VERT-" + channel.upper() + "-"
        if setting in ("coupling", "probe"):
            plan = _menu_plan(snapshot, channel)
            if plan is not None:
                return plan
            raw_key = prefix + ("COUP" if setting == "coupling" else "PROBE")
            values = _enum_map(key)
            current_raw = _raw(snapshot, raw_key)
            indices = sorted(values)
            if current_raw not in values or not _equal(_state(snapshot, key), values[current_raw]):
                raise SetupError(f"Unknown or inconsistent {key} enumeration")
            next_raw = indices[(indices.index(current_raw) + 1) % len(indices)]
            return _value_plan(snapshot, key, raw_key, next_raw, values[next_raw],
                               "softkey-1" if setting == "coupling" else "softkey-4",
                               dependency_channel=channel if setting == "probe" else None)
        if setting == "volts_per_div":
            probe = _state(snapshot, channel + ".probe")
            values = scope_settings.VOLTS_PER_DIV
            raw_key = prefix + "VB"
            current_raw = _raw(snapshot, raw_key)
            if current_raw not in values or not _equal(values[current_raw] * probe, _state(snapshot, key)):
                raise SetupError(f"Unknown or inconsistent {key} scale")
            desired_raw = next((index for index, volts in values.items() if _equal(volts * probe, target)), None)
            if desired_raw is None:
                raise SetupError(f"{key} cannot be reached at the current probe factor")
            direction = 1 if desired_raw > current_raw else -1
            next_raw = current_raw + direction
            if next_raw not in values:
                raise SetupError("Scale step falls outside the verified range table")
            return _value_plan(snapshot, key, raw_key, next_raw, values[next_raw] * probe,
                               channel + ("-scale-plus" if direction > 0 else "-scale-minus"),
                               dependency_channel=channel)
        if setting == "position_div":
            raw_key = prefix + "POS"
            current_raw = _raw(snapshot, raw_key)
            if not _equal(current_raw / 25, _state(snapshot, key)):
                raise SetupError(f"Unknown or inconsistent {key} position")
            desired_raw = _central(target * 25, key)
            direction = 1 if desired_raw > current_raw else -1
            next_raw = _central(current_raw + direction, key)
            return _value_plan(snapshot, key, raw_key, next_raw, next_raw / 25,
                               channel + ("-position-plus" if direction > 0 else "-position-minus"),
                               dependency_channel=channel)
    if key == "horizontal.seconds_per_div":
        values = scope_settings.SECONDS_PER_DIV
        current_raw = _raw(snapshot, "HORIZ-TB")
        if current_raw not in values or not _equal(values[current_raw], _state(snapshot, key)):
            raise SetupError("Unknown or inconsistent main timebase")
        desired_raw = next((index for index, seconds in values.items() if _equal(seconds, target)), None)
        if desired_raw is None:
            raise SetupError("Timebase is outside the verified table")
        direction = 1 if desired_raw > current_raw else -1
        next_raw = current_raw + direction
        if next_raw not in values:
            raise SetupError("Timebase step falls outside the verified table")
        return _value_plan(snapshot, key, "HORIZ-TB", next_raw, values[next_raw],
                           "timebase-plus" if direction > 0 else "timebase-minus",
                           additional_fields=frozenset(("HORIZ-WIN-TB",)),
                           expected_additional={"HORIZ-WIN-TB": next_raw})
    if key.startswith("trigger."):
        if key == "trigger.type":
            raise SetupError("Trigger-type transitions are not enabled")
        if key == "trigger.level_volts":
            source = _state(snapshot, "trigger.source")
            if source not in ("ch1", "ch2") or _state(snapshot, source + ".enabled") is not True:
                raise SetupError("Absolute trigger level requires an enabled CH1 or CH2 source")
            volts = _number(_state(snapshot, source + ".volts_per_div"), source + ".volts_per_div")
            position = _raw(snapshot, "VERT-" + source.upper() + "-POS")
            current_raw = _raw(snapshot, "TRIG-VPOS")
            if not _equal((current_raw - position) * volts / 25, _state(snapshot, key)):
                raise SetupError("Trigger level is inconsistent with its validated raw fields")
            desired_raw = _central(target * 25 / volts + position, key)
            direction = 1 if desired_raw > current_raw else -1
            next_raw = _central(current_raw + direction, key)
            if abs(next_raw - position) > 100:
                raise SetupError("Trigger-level gesture exceeds the ±4-division operating bound")
            return _value_plan(snapshot, key, "TRIG-VPOS", next_raw, (next_raw - position) * volts / 25,
                               "trigger-level-plus" if direction > 0 else "trigger-level-minus")
        plan = _menu_plan(snapshot, "trigger")
        if plan is not None:
            return plan
        raw_key, control = {
            "trigger.source": ("TRIG-SRC", "softkey-2"),
            "trigger.slope": ("TRIG-EDGE-SLOPE", "softkey-3"),
            "trigger.mode": ("TRIG-MODE", "softkey-4"),
            "trigger.coupling": ("TRIG-COUP", "softkey-5"),
        }[key]
        values = _enum_map(key)
        current_raw = _raw(snapshot, raw_key)
        indices = sorted(values)
        if current_raw not in values or not _equal(_state(snapshot, key), values[current_raw]):
            raise SetupError(f"Unknown or inconsistent {key} enumeration")
        next_raw = indices[(indices.index(current_raw) + 1) % len(indices)]
        mirrors = {"TRIG-SWAP-CH1-MODE": next_raw, "TRIG-SWAP-CH2-MODE": next_raw} \
            if key == "trigger.mode" else {}
        extra = frozenset(("TRIG-VPOS",)) if key == "trigger.source" else frozenset(mirrors)
        return _value_plan(snapshot, key, raw_key, next_raw, values[next_raw], control,
                           additional_fields=extra, expected_additional=mirrors)
    raise SetupError(f"No verified front-panel mapping is available for {key}")


def configure(driver, target, journal, *, clock=time.monotonic, max_steps=MAX_STEPS,
              timeout_seconds=MAX_SECONDS):
    """Converge to a validated flat target, or raise SetupError with partial result.

    The driver's read() returns a freshly decoded snapshot; press(control_id)
    performs exactly one gesture. The caller must durably persist each journal
    callback before returning. Deadlines bound decisions between driver calls;
    the driver's own transfer deadlines must also be bounded.
    """
    canonical = validate_target({"schema_version": 1, "settings": target})
    if type(max_steps) is not int or not 1 <= max_steps <= MAX_STEPS:
        raise SetupError(f"max_steps must be an integer from 1 to {MAX_STEPS}")
    duration = _number(timeout_seconds, "timeout_seconds")
    if not 0 < duration <= MAX_SECONDS:
        raise SetupError(f"timeout_seconds must be greater than zero and at most {MAX_SECONDS}")
    if not callable(journal) or not callable(clock) or not callable(getattr(driver, "read", None)) or \
            not callable(getattr(driver, "press", None)):
        raise SetupError("Configuration requires a driver, durable journal and monotonic clock")
    started = clock()
    result = {"status": "in_progress", "target": canonical, "initial": None,
              "final": None, "steps": 0, "elapsed_seconds": 0.0}

    def check_deadline():
        elapsed = clock() - started
        result["elapsed_seconds"] = elapsed
        if not math.isfinite(elapsed) or elapsed < 0 or elapsed >= duration:
            raise SetupError("Configuration deadline expired or monotonic clock became invalid")

    def record(event, **fields):
        journal(deepcopy({"event": event, "step": result["steps"], **fields}))

    def read():
        check_deadline()
        received = driver.read()
        record("read", snapshot=received)
        snapshot = _snapshot(received)
        result["final"] = snapshot
        check_deadline()
        return snapshot

    try:
        record("begin", target=canonical, max_steps=max_steps, timeout_seconds=duration)
        current = read()
        result["initial"] = deepcopy(current)
        _preflight(current, canonical)
        for key, desired in canonical.items():
            while not _equal(_state(current, key), desired):
                check_deadline()
                if result["steps"] >= max_steps:
                    raise SetupError("Configuration step budget exhausted")
                control, allowed, verify = _next_action(current, key, desired, canonical)
                record("before_press", step=result["steps"] + 1, control=control,
                       setting=key, before=_state(current, key), target=desired)
                check_deadline()
                result["steps"] += 1
                driver.press(control)
                previous, current = current, read()
                _guard(previous, current, allowed)
                verify(previous, current)
                _preflight(current, canonical)
        for key, desired in canonical.items():
            if not _equal(_state(current, key), desired):
                raise SetupError(f"Final readback no longer matches {key}")
        check_deadline()
        result["status"] = "verified"
        record("verified", target=canonical)
        return result
    except (Exception, KeyboardInterrupt) as error:
        result["status"] = "aborted"
        message = str(error) or type(error).__name__
        result["error"] = message
        try:
            record("aborted", error=message)
        except (Exception, KeyboardInterrupt):
            pass  # A failed journal must never permit another device write.
        raise SetupError(message, deepcopy(result)) from error
