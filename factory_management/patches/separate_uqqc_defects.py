"""Seed independent UQQC catalogs while preserving existing event and offline IDs."""

import frappe

from factory_management.uqqc.i18n import text
from factory_management.uqqc.provision import ensure_schema


PATCH_NAME = "factory_management.patches.separate_uqqc_defects"
EVENT_TYPE = "UQQC Inspection Event"
CATALOGS = (
    ("QC Defect Group", "UQQC Defect Group", ("code", "title", "is_active", "legacy_id")),
    ("QC Defect Position Group", "UQQC Defect Position Group", ("code", "title", "is_active", "legacy_id")),
    ("QC Defect", "UQQC Defect", ("code", "title", "defect_group", "severity", "is_active", "legacy_id")),
    ("QC Defect Position", "UQQC Defect Position", ("code", "title", "position_group", "is_active", "legacy_id")),
)
EVENT_LINKS = {
    "defect": ("QC Defect", "UQQC Defect"),
    "defect_position": ("QC Defect Position", "UQQC Defect Position"),
}


def _field_options(fieldname):
    return frappe.db.get_value("DocField", {"parent": EVENT_TYPE, "fieldname": fieldname}, "options")


def _catalog_rows():
    result = {}
    for source, _, fields in CATALOGS:
        result[source] = (frappe.get_all(source, fields=["name", *fields], order_by="name",
                                         limit_page_length=0)
                          if frappe.db.exists("DocType", source) else [])
    return result


def _validate_source_groups(rows):
    for source, group_source, fieldname in (
        ("QC Defect", "QC Defect Group", "defect_group"),
        ("QC Defect Position", "QC Defect Position Group", "position_group"),
    ):
        known = {row.name for row in rows[group_source]}
        for row in rows[source]:
            if row.get(fieldname) not in known:
                frappe.throw(text("catalog.missing_group").format(
                    doctype=source, record=row.name, group=row.get(fieldname) or ""),
                    frappe.ValidationError)


def _copy_missing(rows):
    for source, target, fields in CATALOGS:
        for row in rows[source]:
            if frappe.db.exists(target, row.name):
                continue
            frappe.get_doc({"doctype": target, "name": row.name,
                            **{field: row.get(field) for field in fields}}).insert(
                                ignore_permissions=True, set_name=row.name)


def _validate_history():
    for fieldname, (_, target) in EVENT_LINKS.items():
        result = frappe.db.sql(
            f"""SELECT e.name AS event_name, e.`{fieldname}` AS reference
                FROM `tab{EVENT_TYPE}` e
                LEFT JOIN `tab{target}` master ON master.name = e.`{fieldname}`
                WHERE COALESCE(e.`{fieldname}`, '') != '' AND master.name IS NULL
                LIMIT 1""", as_dict=True,
        )
        if result:
            frappe.throw(text("catalog.missing_history").format(
                event=result[0].event_name, reference=result[0].reference),
                frappe.ValidationError)


def _retarget_event_links():
    for fieldname, (source, target) in EVENT_LINKS.items():
        row = frappe.db.get_value("DocField", {"parent": EVENT_TYPE, "fieldname": fieldname},
                                  ["name", "options"], as_dict=True)
        if not row or row.options not in (source, target):
            frappe.throw(text("catalog.event_link_conflict").format(field=fieldname),
                         frappe.ValidationError)
        if row.options == source:
            frappe.db.set_value("DocField", row.name, "options", target, update_modified=False)
    frappe.clear_cache(doctype=EVENT_TYPE)


def execute():
    if frappe.db.exists("Patch Log", PATCH_NAME):
        return
    existed = bool(frappe.db.exists("DocType", EVENT_TYPE))
    old_options = {fieldname: _field_options(fieldname) for fieldname in EVENT_LINKS} if existed else {}
    for fieldname, (source, target) in EVENT_LINKS.items():
        if existed and old_options[fieldname] not in (source, target):
            frappe.throw(text("catalog.event_link_conflict").format(field=fieldname),
                         frappe.ValidationError)
    ensure_schema()
    rows = _catalog_rows()
    needs_copy = (not existed or any(old_options[fieldname] == source
                                     for fieldname, (source, _) in EVENT_LINKS.items()))
    if not needs_copy and not any(frappe.db.count(target) for _, target, _ in CATALOGS):
        needs_copy = bool(any(rows.values()) and not frappe.db.count(EVENT_TYPE))
    if needs_copy:
        _validate_source_groups(rows)
        _copy_missing(rows)
    _validate_history()
    _retarget_event_links()
