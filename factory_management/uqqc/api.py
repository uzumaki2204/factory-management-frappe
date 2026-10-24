"""Validated services called by the six Desk-editable UQQC Server Scripts."""

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import frappe
from frappe.query_builder.functions import Max, Sum
from frappe.utils.caching import request_cache

from factory_management import api as qc
from factory_management import device_registry
from factory_management.uqqc.access import approved_device, endpoint_policy, find_device, token, token_pairing
from factory_management.uqqc.i18n import fail, text


EVENT_TYPE = "UQQC Inspection Event"
SCOPE = {"lineId": "line", "productId": "product", "colorId": "color", "sizeId": "size", "marketId": "market"}
LINKS = {"line": "Production Line", "product": "Product", "color": "Product Color", "size": "Size", "market": "Market"}


class UQQCSyncRetryError(frappe.ValidationError):
    http_status_code = 409


def clock():
    return {_camel(key): value for key, value in qc._clock().items()}


def _camel(key):
    first, *rest = key.split("_")
    return first + "".join(part.title() for part in rest)


def _device_data(device, pairing):
    ready = device.status == "Approved" and bool(device.is_active) and bool(device.company) and pairing == "Paired"
    return {
        "id": device.name, "deviceUid": device.device_uid, "deviceName": device.device_name,
        "status": device.status if ready or device.status in ("Rejected", "Deactivated") else "PendingApproval",
        "isActive": ready, "pairingStatus": pairing, "companyId": device.company,
        "companyName": frappe.db.get_value("Company", device.company, "company_name") if device.company else "",
        "factoryId": device.factory, "lineId": device.line,
    }


def device_register(data, endpoint):
    device_id = data.get("deviceId")
    try:
        device_id = str(uuid.UUID(str(device_id)))
    except (ValueError, TypeError):
        fail("api.device_id")
    secret = token()
    if len(secret) < 32 or len(secret) > 256:
        fail("api.token", permission=True)
    device = find_device(device_id)
    pairing = token_pairing(device, secret)
    if pairing in ("Rejected", "Revoked"):
        fail("api.token", permission=True)
    if not pairing:
        pairing, _ = device_registry.register_client(
            device, "uqqc", secret, data.get("browserName"), data.get("operatingSystem"),
        )
        if not pairing or pairing in ("Rejected", "Revoked"):
            fail("api.token", permission=True)
    return _device_data(device, pairing)


def device_check(data, endpoint):
    device = find_device(data.get("deviceId"))
    pairing = token_pairing(device, token())
    if not pairing or pairing in ("Rejected", "Revoked"):
        fail("api.token", permission=True)
    return _device_data(device, pairing)


def bootstrap(data, endpoint):
    device = approved_device(data.get("deviceId"), endpoint)
    # Shared production masters and the independent UQQC defect catalogs.
    rows = qc._rows
    definitions = {
        "companies": ("Company", "company_code", "company_name", {"active": 1, "name": device.company}),
        "factories": ("Factory", "factory_code", "factory_name", {"is_active": 1, "company": device.company}),
        "customers": ("Customer", "customer_code", "customer_name", {"is_active": 1}),
        "seasons": ("Production Season", "season_code", "season_name", {"is_active": 1}),
        "products": ("Product", "product_code", "product_name", {"is_active": 1}),
        "colors": ("Product Color", "color_code", "color_name", {"is_active": 1}),
        "sizes": ("Size", "size_code", "size_label", {"is_active": 1}),
        "markets": ("Market", "code", "name_en", {"is_active": 1}),
        "lines": ("Production Line", "line_code", "line_name", {"is_active": 1, "company": device.company}),
        "defectPositionGroups": ("UQQC Defect Position Group", "code", "title", {"is_active": 1}),
    }
    extra = {"products": ["customer", "production_season"], "lines": ["company", "factory"], "factories": ["company"]}
    catalog = {}
    for key, (doctype, code, title, filters) in definitions.items():
        catalog[key] = []
        for row in rows(doctype, ["name", code, title] + extra.get(key, []), filters):
            option = qc._option(row, code, title)
            for field in extra.get(key, []):
                target = "seasonId" if field == "production_season" else field + "Id"
                option[target] = row.get(field)
            catalog[key].append(option)
    valid_ids = {key: {item["id"] for item in values} for key, values in catalog.items()}
    catalog["productVariants"] = [
        {"productId": row.product, "colorId": row.qc_color, "sizeId": row.size, "marketId": row.market}
        for row in rows("Product Variant", ["product", "qc_color", "size", "market"], {"is_active": 1})
        if row.product in valid_ids["products"] and row.qc_color in valid_ids["colors"]
        and row.size in valid_ids["sizes"] and row.market in valid_ids["markets"]
    ]
    groups = {row.name: row for row in rows("UQQC Defect Group", ["name", "code", "title"], {"is_active": 1})}
    catalog["defects"] = [
        {"id": row.name, "code": row.code, "name": row.title, "groupCode": groups[row.defect_group].code,
         "groupName": groups[row.defect_group].title, "severity": row.severity}
        for row in rows("UQQC Defect", ["name", "code", "title", "defect_group", "severity"], {"is_active": 1})
        if row.defect_group in groups
    ]
    positions = {row["id"]: row for row in catalog["defectPositionGroups"]}
    catalog["defectPositions"] = [
        {"id": row.name, "code": row.code, "name": row.title, "positionGroupId": row.position_group,
         "groupCode": positions[row.position_group]["code"], "groupName": positions[row.position_group]["name"]}
        for row in rows("UQQC Defect Position", ["name", "code", "title", "position_group"], {"is_active": 1})
        if row.position_group in positions
    ]
    version = hashlib.sha256(json.dumps(catalog, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {**catalog, "catalogVersion": version, **clock()}


@request_cache
def _master_value(doctype, name, field):
    return frappe.db.get_value(doctype, name, field)


@request_cache
def _variant(product, color, size, market):
    return frappe.db.exists("Product Variant", {"product": product, "qc_color": color, "size": size,
                                               "market": market, "is_active": 1})


def _scope(data, device):
    scope = {field: data.get(key) for key, field in SCOPE.items()}
    for field, doctype in LINKS.items():
        value = scope[field]
        if not isinstance(value, str) or not value or not _master_value(doctype, value, "is_active"):
            fail("api.scope")
    if _master_value("Production Line", scope["line"], "company") != device.company:
        fail("api.line_company", permission=True)
    if not _variant(scope["product"], scope["color"], scope["size"], scope["market"]):
        fail("api.variant")
    return scope


def _event(item, kind, device):
    if not isinstance(item, dict):
        fail("api.input")
    local_id = item.get("localEventId")
    if not isinstance(local_id, str) or not local_id.strip() or len(local_id) > 100:
        fail("api.event_id")
    try:
        occurred = datetime.fromisoformat(str(item.get("occurredAt", "")).replace("Z", "+00:00"))
        if occurred.tzinfo is None or occurred.year < 1000:
            raise ValueError
        occurred = occurred.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        fail("api.timestamp")
    event = {
        **_scope(item, device), "local_event_id": local_id.strip(), "device": device.name,
        "event_kind": kind, "quantity": 1, "occurred_at": occurred.strftime("%Y-%m-%d %H:%M:%S.%f"),
        "server_date_key": occurred.astimezone(qc._time_zone()).date().isoformat(),
    }
    if kind == "defect":
        version = item.get("schemaVersion", 1)
        quantity = item.get("quantityDelta", 1)
        if type(version) is not int or version not in (1, 2) or type(quantity) is not int or quantity != 1:
            fail("api.input")
        defect = item.get("defectId")
        group = _master_value("UQQC Defect", defect, "defect_group") if isinstance(defect, str) and _master_value("UQQC Defect", defect, "is_active") else None
        if not group or not _master_value("UQQC Defect Group", group, "is_active"):
            fail("api.defect")
        position = item.get("defectPositionId")
        piece = item.get("defectPieceId")
        if version == 2 and (not position or not piece):
            fail("api.position_piece")
        if position:
            group = _master_value("UQQC Defect Position", position, "position_group") if isinstance(position, str) and _master_value("UQQC Defect Position", position, "is_active") else None
            if not group or not _master_value("UQQC Defect Position Group", group, "is_active"):
                fail("api.position_piece")
        if piece:
            try:
                parsed_piece = uuid.UUID(str(piece))
                if not parsed_piece.int:
                    raise ValueError
                piece = str(parsed_piece)
            except (ValueError, TypeError):
                fail("api.position_piece")
        event.update(defect=defect, defect_position=position, defect_piece_id=piece, schema_version=version)
    event["event_uid"] = hashlib.sha256((device.name + "|" + event["local_event_id"].casefold()).encode("utf-8")).hexdigest()
    event["fingerprint"] = hashlib.sha256(json.dumps(event, sort_keys=True).encode("utf-8")).hexdigest()
    return event


def sync(data, endpoint):
    device = approved_device(data.get("deviceId"), for_update=True)
    batches = [(data.get(key, []), kind) for key, kind in (("events", "defect"), ("passEvents", "pass"), ("reworkEvents", "rework"))]
    if any(not isinstance(batch, list) for batch, _ in batches) or sum(len(batch) for batch, _ in batches) > 500:
        fail("api.batch")
    events = [_event(item, kind, device) for batch, kind in batches for item in batch]
    fingerprints = {}
    for event in events:
        uid = event["event_uid"]
        if uid in fingerprints and fingerprints[uid] != event["fingerprint"]:
            fail("api.event_conflict")
        fingerprints[uid] = event["fingerprint"]
    accepted = []
    for event in events:
        uid = event["event_uid"]
        existing = frappe.db.get_value(EVENT_TYPE, uid, "fingerprint")
        if not existing:
            frappe.get_doc({"doctype": EVENT_TYPE, **event, "synced_at": qc._now_db()}).insert(
                ignore_permissions=True, ignore_if_duplicate=True, set_name=uid,
            )
        stored = frappe.db.get_value(EVENT_TYPE, uid, "fingerprint", for_update=True)
        if stored != event["fingerprint"]:
            fail("api.event_conflict")
        accepted.append(event["local_event_id"])
    return {"acceptedCount": len(set(accepted)), "acceptedLocalEventIds": list(dict.fromkeys(accepted))}


def _rows(device, date_key, scope=None):
    event = frappe.qb.DocType(EVENT_TYPE)
    groups = [event[field] for field in (*SCOPE.values(), "event_kind", "defect", "defect_piece_id")]
    query = (frappe.qb.from_(event).select(*groups, Sum(event.quantity).as_("quantity"), Max(event.synced_at).as_("synced_at"))
             .where((event.device == device.name) & (event.server_date_key == date_key)))
    for field, value in (scope or {}).items():
        query = query.where(event[field] == value)
    return query.groupby(*groups).run(as_dict=True)


def _rate(numerator, denominator):
    return float((Decimal(numerator * 100) / Decimal(denominator)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) if denominator else 0


def _totals(rows):
    defects = defaultdict(int)
    passed = rework = legacy_pieces = 0
    pieces = set()
    synced = None
    for row in rows:
        quantity = int(row.quantity)
        if row.event_kind == "pass":
            passed += quantity
        elif row.event_kind == "rework":
            rework += quantity
        else:
            defects[row.defect] += quantity
            if row.defect_piece_id:
                pieces.add(row.defect_piece_id)
            else:
                legacy_pieces += quantity
        if row.synced_at and (not synced or row.synced_at > synced):
            synced = row.synced_at
    defect_no = sum(defects.values())
    defect_pcs = len(pieces) + legacy_pieces
    return {"pass": passed, "rework": rework, "total": passed + rework,
            "passRate": _rate(passed, passed + defect_pcs), "defectNo": defect_no,
            "defectPcs": defect_pcs, "defectPieceIds": sorted(pieces), "totalDefects": defect_no,
            "defectRate": _rate(defect_no, passed + defect_no), "defects": dict(defects), "syncedAt": synced}


def snapshot(data, endpoint):
    device = approved_device(data.get("deviceId"), endpoint)
    moment = clock()
    return {**_totals(_rows(device, moment["serverDateKey"], _scope(data, device))), **moment}


def detail_snapshot(data, endpoint):
    device = approved_device(data.get("deviceId"), endpoint)
    moment = clock()
    groups = defaultdict(list)
    for row in _rows(device, moment["serverDateKey"]):
        groups[tuple(row[field] for field in SCOPE.values())].append(row)
    scopes = [{**dict(zip(SCOPE, key)), **_totals(rows)} for key, rows in sorted(groups.items())]
    return {"scopes": scopes, **moment}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def dispatch(operation: str):
    """Only the configured Server Script URL may invoke the corresponding service."""
    endpoint = endpoint_policy(operation)
    data = dict(frappe.form_dict)
    if frappe.request.method != "GET" and frappe.request.is_json:
        body = frappe.request.get_json(silent=True)
        if not isinstance(body, dict):
            fail("api.input")
        data.update(body)
    handler = {
        "bootstrap": bootstrap, "device_register": device_register, "device_check": device_check,
        "sync": sync, "snapshot": snapshot, "detail_snapshot": detail_snapshot,
    }[operation]
    try:
        return handler(data, endpoint)
    except frappe.QueryDeadlockError:
        if operation != "sync":
            raise
        # Let Frappe roll back the entire request; the durable client queue retries it.
        frappe.throw(text("api.retry_sync"), UQQCSyncRetryError)
