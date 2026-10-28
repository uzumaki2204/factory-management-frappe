"""Shared Frappe device identity and service-specific browser credentials."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import frappe


DEVICE_TYPE = "Factory Device"
CLIENT_TYPE = "Factory Device Client"


@lru_cache(maxsize=1)
def _messages():
    path = Path(__file__).parent / "public" / "js" / "device-i18n.json"
    return json.loads(path.read_text(encoding="utf-8"))


def message(key):
    language = (getattr(frappe.local, "lang", None) or "vi").split("-")[0]
    catalog = _messages()
    return catalog.get(language, catalog["vi"]).get(key, catalog["en"][key])


def _fail(key, error=frappe.ValidationError):
    frappe.throw(message(key), error)


def credential_hash(service_key, secret=None, legacy_hash=None):
    """Keep credentials separate by service without storing plaintext tokens."""
    if legacy_hash is None:
        legacy_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return hashlib.sha256((service_key + ":" + legacy_hash).encode("utf-8")).hexdigest()


def validate_device(doc, method=None):
    uid = (doc.device_uid or "").strip()
    if not uid:
        _fail("error.device_uid")
    doc.device_uid = uid
    existing = frappe.db.get_value(DEVICE_TYPE, {"device_uid": uid}, "name")
    if existing and existing != doc.name:
        _fail("error.duplicate_uid")


def ready(device):
    """A shared device can use either tablet page once it is approved and active."""
    return device.status == "Approved" and bool(device.is_active)


def client_pairing(device, service_key, secret):
    if not isinstance(secret, str) or not 32 <= len(secret) <= 256:
        return None, None
    row = frappe.db.get_value(
        CLIENT_TYPE,
        {"device": device.name, "service_key": service_key,
         "token_hash": credential_hash(service_key, secret)},
        ["name", "status"], as_dict=True,
    )
    if not row:
        return None, None
    if row.status in ("Rejected", "Revoked"):
        return row.status, row.name
    if not ready(device):
        return "Pending", row.name
    if row.status == "Pending":
        frappe.db.set_value(CLIENT_TYPE, row.name, "status", "Approved", update_modified=False)
    return "Paired", row.name


def register_client(device, service_key, secret, browser_name="", operating_system=""):
    if not isinstance(secret, str) or not 32 <= len(secret) <= 256:
        _fail("error.token", frappe.PermissionError)
    digest = credential_hash(service_key, secret)
    existing = frappe.db.get_value(CLIENT_TYPE, {"token_hash": digest},
                                   ["name", "device", "service_key"], as_dict=True)
    if existing and (existing.device != device.name or existing.service_key != service_key):
        _fail("error.token_bound", frappe.PermissionError)
    if not existing:
        frappe.get_doc({
            "doctype": CLIENT_TYPE, "device": device.name, "service_key": service_key,
            "status": "Approved" if ready(device) else "Pending",
            "token_hash": digest, "browser_name": str(browser_name or "")[:140],
            "operating_system": str(operating_system or "")[:140],
        }).insert(ignore_permissions=True, ignore_if_duplicate=True)
    pairing = client_pairing(device, service_key, secret)
    if pairing[0] is None:
        _fail("error.token_bound", frappe.PermissionError)
    return pairing


def import_legacy_client(device_name, service_key, legacy_hash, status,
                         browser_name=None, operating_system=None, last_seen_at=None):
    """Idempotent migration of a hashed legacy client."""
    if not legacy_hash:
        return
    digest = credential_hash(service_key, legacy_hash=legacy_hash)
    existing = frappe.db.get_value(CLIENT_TYPE, {"token_hash": digest},
                                   ["name", "device", "service_key", "status"], as_dict=True)
    if existing:
        if existing.device != device_name or existing.service_key != service_key:
            _fail("error.token_bound")
        return
    frappe.get_doc({
        "doctype": CLIENT_TYPE, "device": device_name, "service_key": service_key,
        "status": status, "token_hash": digest,
        "browser_name": browser_name, "operating_system": operating_system,
        "last_seen_at": last_seen_at,
    }).insert(ignore_permissions=True)
