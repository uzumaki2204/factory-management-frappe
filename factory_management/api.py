"""Guest QC API using the approved Factory Device record ID."""
import hashlib
import json
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import frappe
from factory_management import device_registry
from factory_management import data_epoch as epoch
from factory_management.api_access import require_report_access
from factory_management.i18n import message


@frappe.whitelist(allow_guest=True, methods=["GET"])
def data_epoch():
    return epoch.current()


def _data(value, fallback=None):
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback
    return value


def _fail(key, error=frappe.ValidationError):
    frappe.throw(message(key), error)


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _device_info(doc):
    return {
        "id": doc.name,
        "device_id": doc.name,
        "device_name": doc.device_name,
        "status": doc.status,
        "pairing_status": "Paired" if device_registry.ready(doc) else "Pending",
        "is_active": bool(doc.is_active),
        "company": doc.company,
        "factory": doc.factory,
        "line": doc.line,
        "client_lock_enabled": bool(doc.client_lock_enabled),
    }


def _find_device(device_id):
    if not device_id or not frappe.db.exists(device_registry.DEVICE_TYPE, str(device_id)):
        _fail("error.device_missing", frappe.DoesNotExistError)
    return frappe.get_doc(device_registry.DEVICE_TYPE, str(device_id))


def _approved_device(id):
    doc = _find_device(id)
    if not device_registry.ready(doc):
        _fail("error.pending", frappe.PermissionError)
    now = _now_db()
    frappe.db.set_value(device_registry.DEVICE_TYPE, doc.name, "last_seen_at", now, update_modified=False)
    return doc


def _now_db():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _time_zone():
    name = frappe.db.get_single_value("System Settings", "time_zone") or "Asia/Ho_Chi_Minh"
    try:
        return ZoneInfo(name)
    except KeyError:
        return ZoneInfo("Asia/Ho_Chi_Minh")


def _clock():
    utc = datetime.now(timezone.utc)
    local = utc.astimezone(_time_zone())
    return {
        "server_now_utc": utc.isoformat(),
        "server_utc_offset_minutes": int(local.utcoffset().total_seconds() // 60),
        "server_date_key": local.date().isoformat(),
    }


def _as_utc(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        _fail("error.input")
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _as_db_utc(value):
    return _as_utc(value).strftime("%Y-%m-%d %H:%M:%S.%f")


def _option(row, code, title, **extra):
    value = {"id": row.name, "code": row.get(code) or "", "name": row.get(title) or ""}
    value.update(extra)
    return value


def _rows(doctype, fields, filters=None, limit=20000):
    return frappe.get_all(doctype, fields=fields, filters=filters or {}, order_by="name asc", limit_page_length=limit)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def register_device(id=None, device_id=None, deviceId=None, device_name=None, **_legacy):
    epoch.require_current()
    requested_id = id or device_id or deviceId
    try:
        if requested_id:
            if str(uuid.UUID(str(requested_id))) != str(requested_id).lower():
                _fail("error.input")
        device_id = str(requested_id) if requested_id else str(uuid.uuid4())
    except (TypeError, ValueError):
        _fail("error.input")
    if frappe.db.exists(device_registry.DEVICE_TYPE, device_id):
        doc = frappe.get_doc(device_registry.DEVICE_TYPE, device_id)
    else:
        doc = frappe.get_doc({
            "doctype": device_registry.DEVICE_TYPE,
            "name": device_id,
            "device_name": (device_name or "")[:140],
            "status": "Pending",
            "is_active": 1,
        }).insert(ignore_permissions=True)
    notice_key = "ok.paired" if device_registry.ready(doc) else "ok.register"
    return {"device": _device_info(doc), "notice": message(notice_key)}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def check_device(id=None, device_id=None, deviceId=None):
    epoch.require_current()
    doc = _find_device(id or device_id or deviceId)
    return _device_info(doc)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def bootstrap(id=None, device_id=None, deviceId=None):
    _approved_device(id or device_id or deviceId)
    companies = _rows("Company", ["name", "company_code", "company_name", "active"], {"active": 1})
    factories = _rows("Factory", ["name", "factory_code", "factory_name", "company"], {"is_active": 1})
    customers = _rows("Customer", ["name", "customer_code", "customer_name"], {"is_active": 1})
    seasons = _rows("Production Season", ["name", "season_code", "season_name"], {"is_active": 1})
    products = _rows("Product", ["name", "product_code", "product_name", "customer", "production_season"], {"is_active": 1})
    colors = _rows("Product Color", ["name", "color_code", "color_name"], {"is_active": 1})
    sizes = _rows("ProductSize", ["name", "size_code", "size_label"], {"is_active": 1})
    markets = _rows("Market", ["name", "code", "name_en"], {"is_active": 1})
    variants = _rows("Product Variant", ["name", "product", "product_color", "size", "market"], {"is_active": 1})
    lines = _rows("Production Line", ["name", "line_code", "line_name", "company", "factory"], {"is_active": 1})
    groups = _rows("QC Defect", ["name", "code", "title"], {"is_active": 1, "record_type": "Group"})
    defects = _rows("QC Defect", ["name", "code", "title", "defect_group", "severity"],
                    {"is_active": 1, "record_type": "Defect"})
    position_groups = _rows("QC Defect Position", ["name", "code", "title"],
                            {"is_active": 1, "record_type": "Group"})
    positions = _rows("QC Defect Position", ["name", "code", "title", "position_group"],
                      {"is_active": 1, "record_type": "Position"})
    gm = {x.name: x for x in groups}
    pm = {x.name: x for x in position_groups}
    catalog = {
        "companies": [_option(x, "company_code", "company_name") for x in companies],
        "factories": [_option(x, "factory_code", "factory_name", company_id=x.company) for x in factories],
        "customers": [_option(x, "customer_code", "customer_name") for x in customers],
        "seasons": [_option(x, "season_code", "season_name") for x in seasons],
        "products": [_option(x, "product_code", "product_name", customer_id=x.customer, season_id=x.production_season) for x in products],
        "colors": [_option(x, "color_code", "color_name") for x in colors],
        "sizes": [_option(x, "size_code", "size_label") for x in sizes],
        "markets": [_option(x, "code", "name_en") for x in markets],
        "product_variants": [{"product_id": x.product, "color_id": x.product_color, "size_id": x.size, "market_id": x.market} for x in variants if x.product_color and x.size],
        "lines": [_option(x, "line_code", "line_name", company_id=x.company, factory_id=x.factory) for x in lines],
        "defects": [{"id": x.name, "code": x.code, "name": x.title, "group_code": gm[x.defect_group].code if x.defect_group in gm else "", "group_name": gm[x.defect_group].title if x.defect_group in gm else "", "severity": x.severity} for x in defects],
        "defect_position_groups": [_option(x, "code", "title") for x in position_groups],
        "defect_positions": [{"id": x.name, "code": x.code, "name": x.title, "position_group_id": x.position_group, "group_code": pm[x.position_group].code if x.position_group in pm else "", "group_name": pm[x.position_group].title if x.position_group in pm else ""} for x in positions],
    }
    version = hashlib.sha256(json.dumps(catalog, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    return {"catalog": catalog, "catalog_version": version, **_clock()}


def _valid_link(doctype, name):
    return not name or frappe.db.exists(doctype, str(name))


def _validate_event(item, device):
    local_id = str(item.get("local_event_id") or "").strip()
    if not local_id or len(local_id) > 100:
        _fail("error.event_id")
    links = {"product": "Product", "line": "Production Line", "color": "Product Color",
             "size": "ProductSize", "defect": "QC Defect"}
    for field, dt in links.items():
        if not _valid_link(dt, item.get(field)):
            _fail("error.unknown_master")
    defect = item.get("defect")
    if defect and (frappe.db.get_value("QC Defect", defect, "record_type") != "Defect" or
                   not frappe.db.get_value("QC Defect", defect, "is_active")):
        _fail("error.unknown_master")
    line = item.get("line") or device.line
    if line:
        if not device.company or frappe.db.get_value("Production Line", line, "company") != device.company:
            _fail("error.line_company", frappe.PermissionError)
    return local_id


@frappe.whitelist(allow_guest=True, methods=["POST"])
def sync_events(device_id=None, events=None, id=None, deviceId=None):
    epoch.require_current()
    device = _approved_device(id or device_id or deviceId)
    items = _data(events, [])
    if not isinstance(items, list) or len(items) > 500:
        _fail("error.input")
    local_ids = [_validate_event(item, device) for item in items]
    accepted = []
    created = 0
    for item, local_id in zip(items, local_ids):
        uid = _digest(device.name + "|" + local_id.casefold())
        if not frappe.db.exists("QC Inspection Event", {"event_uid": uid}):
            occurred = _as_utc(item.get("occurred_at") or datetime.now(timezone.utc).isoformat())
            doc = frappe.get_doc({
                "doctype": "QC Inspection Event",
                "event_uid": uid,
                "local_event_id": local_id,
                "device": device.name,
                "event_type": str(item.get("event_type") or "")[:100],
                "product": item.get("product"),
                "line": item.get("line") or device.line,
                "color": item.get("color"),
                "size": item.get("size"),
                "defect": item.get("defect"),
                "quantity_delta": int(item.get("quantity_delta") or 0),
                "occurred_at": occurred.strftime("%Y-%m-%d %H:%M:%S.%f"),
                "synced_at": _now_db(),
                "server_date_key": occurred.astimezone(_time_zone()).date().isoformat(),
            }).insert(ignore_permissions=True)
            created += 1
        accepted.append(local_id)
    return {"accepted_count": created, "accepted_local_event_ids": accepted, "notice": message("ok.events")}


def _is_defect(item):
    return item.defect and item.event_type in ("DefectAdd", "DefectSubtract")


def _is_received(item):
    return item.event_type in ("CumulativeAdd", "CumulativeSubtract")


@frappe.whitelist(allow_guest=True, methods=["POST"])
def snapshot(device_id=None, product=None, line=None, color=None, size=None, id=None, deviceId=None):
    device = _approved_device(id or device_id or deviceId)
    now = datetime.now(_time_zone())
    start = datetime.combine(now.date(), time.min, _time_zone()).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    filters = {"device": device.name,
               "occurred_at": ["between", [start.strftime("%Y-%m-%d %H:%M:%S"), (end - timedelta(microseconds=1)).strftime("%Y-%m-%d %H:%M:%S.%f")]]}
    for key, value in (("product", product), ("line", line or device.line)):
        if value:
            filters[key] = value
    items = _rows("QC Inspection Event",
                  ["event_type", "defect", "quantity_delta", "color", "size", "synced_at", "occurred_at"],
                  filters, limit=100000)
    items.sort(key=lambda x: x.occurred_at)
    received = 0
    defects = defaultdict(int)
    synced = None
    for item in items:
        if (item.color or None) != (color or None) or (item.size or None) != (size or None):
            continue
        synced = max(str(synced or ""), str(item.synced_at or "")) or None
        if _is_defect(item):
            defects[item.defect] = max(0, defects[item.defect] + int(item.quantity_delta or 0))
        elif _is_received(item):
            received = max(0, received + int(item.quantity_delta or 0))
    return {"received": received, "pass": max(0, received - sum(defects.values())),
            "defects": dict(defects), "received_by_defect": {}, "synced_at": synced, **_clock()}



@frappe.whitelist(allow_guest=True, methods=["POST"])
def detail_snapshot(device_id=None, pending_ids=None, id=None, deviceId=None):
    device = _approved_device(id or device_id or deviceId)
    pending = _data(pending_ids, [])
    if (not isinstance(pending, list) or len(pending) > 10000 or
            any(not isinstance(value, str) or len(value) > 100 for value in pending)):
        _fail("error.input")
    now = datetime.now(_time_zone())
    start = datetime.combine(now.date(), time.min, _time_zone()).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    items = _rows(
        "QC Inspection Event",
        ["local_event_id", "product", "line", "defect", "event_type", "quantity_delta", "occurred_at"],
        {"device": device.name,
         "occurred_at": ["between", [start.strftime("%Y-%m-%d %H:%M:%S"),
                                    (end - timedelta(microseconds=1)).strftime("%Y-%m-%d %H:%M:%S.%f")]]},
        limit=100000,
    )
    items.sort(key=lambda item: item.occurred_at)
    wanted = set(pending)
    already_synced = set()
    received = defaultdict(int)
    defects = defaultdict(int)
    for item in items:
        if item.local_event_id in wanted:
            already_synced.add(item.local_event_id)
        product = item.product or ""
        line = item.line or device.line or ""
        if not product or not line:
            continue
        quantity = int(item.quantity_delta or 0)
        if _is_defect(item):
            key = (product, line, item.defect)
            defects[key] = max(0, defects[key] + quantity)
        elif _is_received(item):
            key = (product, line)
            received[key] = max(0, received[key] + quantity)
    return {
        "received": [{"product": key[0], "line": key[1], "quantity": quantity}
                     for key, quantity in received.items()],
        "defects": [{"product": key[0], "line": key[1], "defect": key[2], "quantity": quantity}
                    for key, quantity in defects.items()],
        "already_synced": sorted(already_synced),
        **_clock(),
    }


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_favorites(device_id=None, id=None, deviceId=None):
    device = _approved_device(id or device_id or deviceId)
    rows = _rows("QC Favorite", ["defect", "modified"], {"device": device.name})
    return {"defect_ids": [x.defect for x in rows],
            "updated_at_utc": max((str(x.modified) for x in rows), default=None)}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def replace_favorites(device_id=None, defect_ids=None, id=None, deviceId=None):
    epoch.require_current()
    device = _approved_device(id or device_id or deviceId)
    wanted = set(str(x) for x in _data(defect_ids, []) or [])
    if len(wanted) > 200 or any(
        not frappe.db.exists("QC Defect", x) or
        frappe.db.get_value("QC Defect", x, "record_type") != "Defect" or
        not frappe.db.get_value("QC Defect", x, "is_active")
        for x in wanted
    ):
        _fail("error.unknown_master")
    existing = _rows("QC Favorite", ["name", "defect"], {"device": device.name})
    have = {x.defect: x.name for x in existing}
    for defect in set(have) - wanted:
        frappe.delete_doc("QC Favorite", have[defect], ignore_permissions=True)
    for defect in wanted - set(have):
        frappe.get_doc({"doctype": "QC Favorite", "favorite_uid": _digest(device.name + "|" + defect),
                        "device": device.name, "defect": defect}).insert(ignore_permissions=True)
    return {"defect_ids": sorted(wanted), "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "notice": message("ok.favorites")}


def _report_rows(operation_id, date_from, date_to, **filters):
    require_report_access(operation_id)
    try:
        begin = date.fromisoformat(date_from)
        finish = date.fromisoformat(date_to)
    except (TypeError, ValueError):
        _fail("error.range")
    if begin > finish:
        begin, finish = finish, begin
    if (finish - begin).days > 6:
        _fail("error.range")
    start = datetime.combine(begin, time.min, _time_zone()).astimezone(timezone.utc)
    end = datetime.combine(finish + timedelta(days=1), time.min, _time_zone()).astimezone(timezone.utc)
    where = {"occurred_at": ["between", [start.strftime("%Y-%m-%d %H:%M:%S"),
                                         (end - timedelta(microseconds=1)).strftime("%Y-%m-%d %H:%M:%S.%f")]]}
    where.update({k: v for k, v in filters.items() if v})
    return _rows("QC Inspection Event",
                 ["name", "device", "event_type", "product", "line",
                  "color", "size", "defect", "quantity_delta", "occurred_at", "synced_at"],
                 where, limit=100000)


@frappe.whitelist(methods=["GET"])
def report_detail(date_from=None, date_to=None, event_type=None, device=None, product=None,
                  line=None, color=None, size=None, defect=None):
    rows = _report_rows("qcReportDetail", date_from, date_to, event_type=event_type, device=device,
                        product=product, line=line, color=color, size=size, defect=defect)
    return [dict(x) for x in rows]


@frappe.whitelist(methods=["GET"])
def report_summary(date_from=None, date_to=None, event_type=None, device=None, product=None,
                   line=None, color=None, size=None, defect=None):
    rows = _report_rows("qcReportSummary", date_from, date_to, event_type=event_type, device=device,
                        product=product, line=line, color=color, size=size, defect=defect)
    totals = defaultdict(int)
    for row in rows:
        key = (_as_utc(row.occurred_at).astimezone(_time_zone()).date().isoformat(),
               row.device, row.product, row.line,
               row.event_type, row.defect)
        totals[key] += int(row.quantity_delta or 0)
    return [{"date": key[0], "device": key[1], "product": key[2], "line": key[3],
             "event_type": key[4], "defect": key[5], "quantity": value}
            for key, value in sorted(totals.items(), key=lambda x: str(x[0]))]

