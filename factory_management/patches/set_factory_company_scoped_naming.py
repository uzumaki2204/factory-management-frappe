"""Make Factory names unique within their company while preserving factory codes."""

import frappe
from frappe.model.naming import validate_name
from frappe.model.rename_doc import rename_doc

from factory_management.device_registry import message


DOCTYPE = "Factory"
AUTONAME = "field:factory_key"
MAX_NAME_LENGTH = 140


def _desired_name(row):
    code = (row.factory_code or "").strip()
    company = (row.company or "").strip()
    if (
        not code
        or not company
        or code != row.factory_code
        or company != row.company
        or not frappe.db.exists("Company", company)
    ):
        return None

    name = f"{code}-{company}"
    if len(name) > MAX_NAME_LENGTH:
        return None

    try:
        return validate_name(DOCTYPE, name)
    except frappe.NameError:
        return None


def _plan_renames():
    if not frappe.db.exists("DocType", DOCTYPE):
        frappe.throw(
            message("error.naming_doctype_missing").format(doctype=DOCTYPE),
            frappe.ValidationError,
        )
    if not frappe.db.table_exists(DOCTYPE):
        return []

    rows = frappe.get_all(
        DOCTYPE,
        fields=["name", "factory_code", "company", "legacy_id"],
        order_by="name asc",
        limit_page_length=0,
    )
    plans = []
    targets = {}
    invalid = []

    for row in rows:
        target = _desired_name(row)
        if not target:
            invalid.append(row.name)
            continue

        normalized = target.casefold()
        if normalized in targets:
            frappe.throw(
                message("error.factory_identity_duplicate").format(
                    code=row.factory_code,
                    company=row.company,
                ),
                frappe.ValidationError,
            )
        targets[normalized] = row.name
        plans.append((row.name, target, row.legacy_id))

    if invalid:
        frappe.throw(
            message("error.factory_identity_invalid").format(factory=invalid[0]),
            frappe.ValidationError,
        )

    return plans


def _sync_legacy_maps(plans):
    if not frappe.db.table_exists("QC Legacy Map"):
        return

    legacy_name_by_id = {
        legacy_id: target
        for _, target, legacy_id in plans
        if legacy_id
    }
    mappings = frappe.get_all(
        "QC Legacy Map",
        filters={"source_table": "Factories", "target_doctype": DOCTYPE},
        fields=["name", "legacy_id", "target_name"],
        limit_page_length=0,
    )
    for mapping in mappings:
        target = legacy_name_by_id.get(mapping.legacy_id)
        if target and mapping.target_name != target:
            frappe.db.set_value(
                "QC Legacy Map", mapping.name, "target_name", target,
                update_modified=False,
            )


def _ensure_naming_schema():
    factory_type = frappe.get_doc("DocType", DOCTYPE)
    code_field = next((row for row in factory_type.fields if row.fieldname == "factory_code"), None)
    key_field = next((row for row in factory_type.fields if row.fieldname == "factory_key"), None)
    company_field = next((row for row in factory_type.fields if row.fieldname == "company"), None)
    if not code_field or not company_field:
        frappe.throw(
            message("error.factory_identity_invalid").format(factory=DOCTYPE),
            frappe.ValidationError,
        )

    if not key_field:
        key_field = factory_type.append("fields", {
            "fieldname": "factory_key",
            "label": "Factory Key",
            "fieldtype": "Data",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "reqd": 0,
        })

    # The metadata snapshots are applied by after_migrate, which runs after this
    # post_model_sync patch. Save the required field and naming metadata here so
    # DocType.on_update creates the column before this patch backfills it.
    for fieldname, value in {
        "label": "Factory Key",
        "fieldtype": "Data",
        "hidden": 1,
        "read_only": 1,
        "no_copy": 1,
        "reqd": 0,
    }.items():
        key_field.set(fieldname, value)

    factory_type.naming_rule = "By fieldname"
    factory_type.autoname = AUTONAME
    factory_type.allow_rename = 1
    code_field.reqd = 1
    company_field.reqd = 1

    # Saving even when the field metadata already exists makes this safe to
    # rerun after a failed migrate that left metadata behind but not the column.
    factory_type.save(ignore_permissions=True)
    frappe.clear_cache(doctype=DOCTYPE)

    if not frappe.db.has_column(DOCTYPE, "factory_key"):
        frappe.throw(
            message("error.factory_key_schema_missing").format(doctype=DOCTYPE),
            frappe.ValidationError,
        )


def execute():
    _ensure_naming_schema()
    plans = _plan_renames()
    if not plans:
        return

    # Stage every changing name so code-to-name collisions cannot overwrite records.
    staged = []
    for old_name, target, legacy_id in plans:
        if old_name == target:
            continue

        temporary = "factory-migration-" + frappe.generate_hash(length=24)
        while frappe.db.exists(DOCTYPE, temporary):
            temporary = "factory-migration-" + frappe.generate_hash(length=24)

        rename_doc(
            DOCTYPE, old_name, temporary,
            force=True, ignore_permissions=True, show_alert=False, rebuild_search=False,
        )
        staged.append((temporary, target, legacy_id))

    for temporary, target, _ in staged:
        rename_doc(
            DOCTYPE, temporary, target,
            force=True, ignore_permissions=True, show_alert=False, rebuild_search=False,
        )

    for _, target, _ in plans:
        frappe.db.set_value(DOCTYPE, target, "factory_key", target, update_modified=False)

    _sync_legacy_maps(plans)
    frappe.clear_cache(doctype=DOCTYPE)
