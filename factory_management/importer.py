"""Idempotent SQL Server master and device import, called only by System Manager."""
import hashlib
import json

import frappe
from factory_management.api import _data, _fail


SOURCES = {
    "Companies": ("Company", "company_code"),
    "Factories": ("Factory", "factory_code"),
    "Customers": ("Customer", "customer_code"),
    "ProductionSeasons": ("Production Season", "season_code"),
    "Products": ("Product", "product_code"),
    "Colors": ("Product Color", "color_code"),
    "Sizes": ("Size", "size_code"),
    "Markets": ("Market", "code"),
    "ProductVariants": ("Product Variant", None),
    "ProductionLines": ("Production Line", "line_code"),
    "LineGroups": ("Line Group", "group_code"),
    "LineGroupDetails": ("Line Group Assignment", "assignment_uid"),
    "QCDefectGroups": ("QC Defect Group", "code"),
    "QCDefects": ("QC Defect", "code"),
    "QCDefectPositionGroups": ("QC Defect Position Group", "code"),
    "QCDefectPositions": ("QC Defect Position", "code"),
    "Devices": ("Factory Device", "device_id"),
}
DEVICE_STATUSES = {status.casefold(): status for status in ("Pending", "Approved", "Rejected", "Deactivated")}


def _admin():
    user = frappe.session.user
    if user != "Administrator" and "System Manager" not in frappe.get_roles(user):
        _fail("error.admin", frappe.PermissionError)


def _uid(table, legacy_id):
    return hashlib.sha256((table + "|" + legacy_id.lower()).encode("utf-8")).hexdigest()


def _mapped(table, legacy_id):
    if not legacy_id:
        return None
    return frappe.db.get_value("QC Legacy Map", {"mapping_uid": _uid(table, str(legacy_id))}, "target_name")


def _target(table, legacy_id):
    if not legacy_id:
        return None
    target = _mapped(table, legacy_id)
    if not target:
        _fail("error.unknown_master")
    return target


def _save_map(table, legacy_id, doctype, name):
    key = _uid(table, legacy_id)
    if frappe.db.exists("QC Legacy Map", {"mapping_uid": key}):
        return
    frappe.get_doc({
        "doctype": "QC Legacy Map",
        "mapping_uid": key,
        "source_table": table,
        "legacy_id": legacy_id,
        "target_doctype": doctype,
        "target_name": name,
    }).insert(ignore_permissions=True)


def _new(dt, values):
    return frappe.get_doc({"doctype": dt, **values}).insert(ignore_permissions=True).name


def _active(row):
    return int(bool(row.get("IsActive", True)))


def _code(row):
    return str(row.get("Code") or "").strip()


def _name(row):
    return str(row.get("Name") or "").strip()


def _values(table, row):
    code, title, active, legacy = _code(row), _name(row), _active(row), str(row["Id"])
    if table == "Companies":
        return {"company_code": code, "company_name": title, "active": active}
    if table == "Factories":
        return {"factory_code": code, "factory_name": title,
                "company": _target("Companies", row.get("CompanyId")), "is_active": active,
                "legacy_id": legacy}
    if table == "Customers":
        return {"customer_code": code, "customer_name": title, "is_active": active, "legacy_id": legacy}
    if table == "ProductionSeasons":
        return {"season_code": code, "season_name": title,
                "from_date": row.get("FromDate"), "to_date": row.get("ToDate"),
                "is_active": active, "legacy_id": legacy}
    if table == "Products":
        season = _target("ProductionSeasons", row.get("SeasonId"))
        return {"product_code": code, "product_name": title, "is_active": active,
                "customer": _target("Customers", row.get("CustomerId")),
                "production_season": season, "season": frappe.db.get_value("Production Season", season, "season_name") if season else ""}
    if table == "Colors":
        return {"color_code": code, "color_name": title, "is_active": active, "legacy_id": legacy}
    if table == "Sizes":
        return {"size_code": code, "size_label": title,
                "sort_order": row.get("DisplayOrder") or 0, "is_active": active}
    if table == "Markets":
        return {"code": code, "name_en": title, "is_active": active}
    if table == "ProductVariants":
        return {"product": _target("Products", row.get("ProductId")),
                "qc_color": _target("Colors", row.get("ColorId")),
                "size": _target("Sizes", row.get("SizeId")),
                "market": _target("Markets", row.get("MarketId")),
                "is_active": active}
    if table == "LineGroups":
        return {"group_code": code, "group_name": title,
                "company": _target("Companies", row.get("CompanyId")),
                "factory": _target("Factories", row.get("FactoryId")),
                "is_active": active, "legacy_id": legacy}
    if table == "ProductionLines":
        return {"line_code": code, "line_name": title,
                "company": _target("Companies", row.get("CompanyId")),
                "factory": _target("Factories", row.get("FactoryId")),
                "is_active": active, "legacy_id": legacy}
    if table == "QCDefectGroups":
        return {"code": code, "title": title, "is_active": active, "legacy_id": legacy}
    if table == "QCDefects":
        return {"code": code, "title": title, "defect_group": _target("QCDefectGroups", row.get("DefectGroupId")),
                "severity": row.get("Severity") or "", "is_active": active, "legacy_id": legacy}
    if table == "QCDefectPositionGroups":
        return {"code": code, "title": title, "is_active": active, "legacy_id": legacy}
    if table == "QCDefectPositions":
        return {"code": code, "title": title,
                "position_group": _target("QCDefectPositionGroups", row.get("PositionGroupId")),
                "is_active": active, "legacy_id": legacy}
    if table == "Devices":
        status = DEVICE_STATUSES.get(str(row.get("Status") or "Pending").strip().casefold())
        if not status:
            _fail("error.input")
        return {"device_id": legacy, "device_uid": str(row.get("DeviceUid") or "").strip(),
                "device_name": row.get("DeviceName") or "", "status": status,
                "is_active": active,
                "company": _target("Companies", row.get("CompanyId")),
                "factory": _target("Factories", row.get("FactoryId")),
                "line": _target("ProductionLines", row.get("LineId")),
                "client_lock_enabled": int(bool(row.get("ClientLockEnabled", True))),
                "browser_name": row.get("BrowserName") or "",
                "operating_system": row.get("OperatingSystem") or ""}


def _existing(dt, table, values, codefield):
    if table == "ProductVariants":
        key = {k: values.get(k) for k in ("product", "qc_color", "size", "market")}
        return frappe.db.get_value(dt, key, "name")
    if table == "Devices":
        return frappe.db.get_value(dt, {"device_id": values["device_id"]}, "name")
    return frappe.db.get_value(dt, {codefield: values[codefield]}, "name")


def _import_line_group_detail(row):
    legacy = str(row.get("Id") or "").strip()
    if not legacy:
        _fail("error.input")
    existing = frappe.db.get_value("Line Group Assignment", {"legacy_id": legacy}, "name")
    if bool(row.get("IsDeleted")):
        if existing:
            frappe.db.set_value("Line Group Assignment", existing, "is_active", 0)
        return "deleted"
    line = _target("ProductionLines", row.get("LineId"))
    group = _target("LineGroups", row.get("LineGroupId"))
    values = {"line": line, "line_group": group, "is_active": 1}
    if existing:
        doc = frappe.get_doc("Line Group Assignment", existing)
        changed = False
        for key, value in values.items():
            if doc.get(key) != value:
                doc.set(key, value)
                changed = True
        if changed:
            doc.save(ignore_permissions=True)
            return "existing"
        return "mapped"
    _new("Line Group Assignment", {"assignment_uid": _uid("LineGroupDetails", legacy),
                                   "legacy_id": legacy, **values})
    return "created"


def _import_one(table, row):
    if table == "LineGroupDetails":
        return _import_line_group_detail(row)
    if bool(row.get("IsDeleted")):
        return "deleted"
    legacy = str(row.get("Id") or "")
    if not legacy:
        _fail("error.input")
    mapped_name = _mapped(table, legacy)
    if mapped_name:
        if table in ("LineGroups", "ProductionLines"):
            values = _values(table, row)
            doc = frappe.get_doc(SOURCES[table][0], mapped_name)
            changed = False
            for key, value in values.items():
                if doc.get(key) != value:
                    doc.set(key, value)
                    changed = True
            if changed:
                doc.save(ignore_permissions=True)
                return "existing"
        return "mapped"
    dt, codefield = SOURCES[table]
    values = _values(table, row)
    if table != "ProductVariants" and table != "Devices" and not values.get(codefield):
        _fail("error.input")
    if table == "Devices" and not values["device_uid"]:
        _fail("error.input")
    existing = _existing(dt, table, values, codefield)
    if existing:
        if table in ("LineGroups", "ProductionLines"):
            doc = frappe.get_doc(dt, existing)
            changed = False
            for key, value in values.items():
                if doc.get(key) != value:
                    doc.set(key, value)
                    changed = True
            if changed:
                doc.save(ignore_permissions=True)
        if table == "Products":
            doc = frappe.get_doc(dt, existing)
            changed = False
            for key in ("customer", "production_season"):
                if not doc.get(key) and values.get(key):
                    doc.set(key, values[key])
                    changed = True
            if changed:
                doc.save(ignore_permissions=True)
        name = existing
        outcome = "existing"
    else:
        name = _new(dt, values)
        outcome = "created"
    _save_map(table, legacy, dt, name)
    return outcome


@frappe.whitelist(methods=["POST"])
def import_batch(table=None, rows=None):
    _admin()
    if table not in SOURCES:
        _fail("error.input")
    records = _data(rows, [])
    if not isinstance(records, list) or len(records) > 200:
        _fail("error.input")
    counts = {"created": 0, "existing": 0, "mapped": 0, "deleted": 0, "inactive": 0}
    for row in records:
        counts[_import_one(table, row)] += 1
    return {"table": table, **counts}
