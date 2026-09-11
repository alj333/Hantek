"""Local ordinary-control catalog; no USB or executable code is loaded here."""
import json
from pathlib import Path


CATALOG_PATH = Path(__file__).with_name("control_catalog.json")
MAX_ROTARY_COUNT = 5
# Exclude maintenance, help/save menus, panel locks, reset and the Run/Stop
# toggle. The existing explicit acquisition commands remain separate.
ORDINARY_KEYCODES = frozenset(list(range(1, 6)) + list(range(8, 11))
                            + [12, 13, 15, 16, 17, 18] + list(range(23, 48)))


def load_catalog():
    raw = CATALOG_PATH.read_bytes()
    if len(raw) > 65536:
        raise ValueError("Control catalog exceeds its size limit")
    value = json.loads(raw)
    if (not isinstance(value, dict) or value.get("schema_version") != 1
            or value.get("max_rotary_count") != MAX_ROTARY_COUNT
            or not isinstance(value.get("controls"), list)):
        raise ValueError("Invalid control catalog schema")
    seen_ids, seen_keys = set(), set()
    for control in value["controls"]:
        if not isinstance(control, dict):
            raise ValueError("Invalid control entry")
        for key in ("id", "label", "group", "description", "validation"):
            if not isinstance(control.get(key), str) or not control[key]:
                raise ValueError("Control catalog has missing text")
        keycode = control.get("keycode")
        kind = control.get("kind")
        if (type(keycode) is not int or keycode not in ORDINARY_KEYCODES
                or kind not in ("button", "rotary")
                or control.get("max_count") != (MAX_ROTARY_COUNT if kind == "rotary" else 1)
                or type(control.get("context_dependent")) is not bool
                or control["id"] in seen_ids or keycode in seen_keys):
            raise ValueError("Invalid or duplicate ordinary control mapping")
        seen_ids.add(control["id"])
        seen_keys.add(keycode)
    if not seen_ids:
        raise ValueError("The control catalog is empty")
    return value


def public_catalog():
    catalog = load_catalog()
    for control in catalog["controls"]:
        del control["keycode"]
    catalog["hardware_access"] = False
    return catalog


def control_spec(control_id, count=1):
    if not isinstance(control_id, str):
        raise ValueError("Choose a named control from the controls catalog")
    if type(count) is not int or not 1 <= count <= MAX_ROTARY_COUNT:
        raise ValueError("Control count must be an integer from 1 to 5")
    for control in load_catalog()["controls"]:
        if control["id"] == control_id:
            if count > control["max_count"]:
                raise ValueError("Buttons accept exactly one press per request")
            return control
    raise ValueError("Unknown or excluded panel control: " + control_id)


def allowed_payload(payload):
    return (len(payload) == 2 and payload[1] == 1
            and payload[0] in {c["keycode"] for c in load_catalog()["controls"]})
