"""Shared Factory Device identity and approval state."""

import json
import uuid
from functools import lru_cache
from pathlib import Path

import frappe


DEVICE_TYPE = "Factory Device"
CLIENT_TYPE = "Factory Device Client"  # Historical migrations only.


@lru_cache(maxsize=1)
def _messages():
    path = Path(__file__).parent / "public" / "js" / "device-i18n.json"
    return json.loads(path.read_text(encoding="utf-8"))


def message(key):
    language = (getattr(frappe.local, "lang", None) or "vi").split("-")[0]
    catalog = _messages()
    return catalog.get(language, catalog["vi"]).get(key, catalog["en"][key])


def ready(device):
    return device.status == "Approved" and bool(device.is_active)


def before_naming(device, method=None):
    """Keep existing VARCHAR names while assigning UUID record IDs to new devices."""
    name = str(device.name or "").strip()
    if not name:
        device.name = str(uuid.uuid4())
        return
    try:
        valid = str(uuid.UUID(name)) == name.lower()
    except (TypeError, ValueError):
        valid = False
    if not valid:
        frappe.throw(message("error.device_id_invalid"), frappe.ValidationError)
