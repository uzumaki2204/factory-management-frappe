"""Merge group records into the QC/UQQC defect catalog DocTypes."""

import frappe

from factory_management.uqqc.i18n import text


PATCH_NAME = "factory_management.patches.merge_defect_catalogs"
CATALOG_MIGRATIONS = (
    {
        "group_doctype": "QC Defect Group",
        "item_doctype": "QC Defect",
        "parent_field": "defect_group",
        "item_type": "Defect",
        "group_type": "Group",
        "legacy_table": "QCDefectGroups",
    },
    {
        "group_doctype": "QC Defect Position Group",
        "item_doctype": "QC Defect Position",
        "parent_field": "position_group",
        "item_type": "Position",
        "group_type": "Group",
        "legacy_table": "QCDefectPositionGroups",
    },
    {
        "group_doctype": "UQQC Defect Group",
        "item_doctype": "UQQC Defect",
        "parent_field": "defect_group",
        "item_type": "Defect",
        "group_type": "Group",
        "legacy_table": None,
    },
    {
        "group_doctype": "UQQC Defect Position Group",
        "item_doctype": "UQQC Defect Position",
        "parent_field": "position_group",
        "item_type": "Position",
        "group_type": "Group",
        "legacy_table": None,
    },
)
GROUP_FIELDS = ("code", "title", "is_active", "legacy_id")
PERMISSION_FLAGS = (
    "read", "write", "create", "delete", "submit", "cancel", "amend", "report",
    "export", "import", "share", "print", "email", "select",
)
SYSTEM_FIELDS = {
    "name", "doctype", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
    "parent", "parenttype", "parentfield", "_user_tags", "_comments", "_assign", "_liked_by",
}


def _records(doctype, fields):
    if not frappe.db.exists("DocType", doctype) or not frappe.db.table_exists(doctype):
        return []
    available = {field.fieldname for field in frappe.get_meta(doctype).fields}
    selected = [field for field in fields if field in available]
    return frappe.get_all(doctype, fields=["name", *selected], order_by="name asc",
                          limit_page_length=0)


def _new_name(doctype):
    while True:
        name = frappe.generate_hash(length=16)
        if not frappe.db.exists(doctype, name):
            return name


def _capture_groups(doctype):
    if not frappe.db.exists("DocType", doctype) or not frappe.db.table_exists(doctype):
        return []
    fieldnames = [field.fieldname for field in frappe.get_meta(doctype).fields
                  if not getattr(field, "is_virtual", 0)]
    return frappe.get_all(doctype, fields=["name", *fieldnames], order_by="name asc",
                          limit_page_length=0)


def _migrate_custom_fields(source, target):
    fields = frappe.get_all("Custom Field", filters={"dt": source}, fields=["name", "fieldname"],
                            limit_page_length=0)
    keys = [field.fieldname for field in frappe.get_meta("Custom Field").fields
            if field.fieldname not in SYSTEM_FIELDS | {"dt", "fieldname"}]
    for item in fields:
        source_doc = frappe.get_doc("Custom Field", item.name)
        existing_name = frappe.db.get_value("Custom Field", {"dt": target, "fieldname": item.fieldname}, "name")
        if existing_name:
            existing = frappe.get_doc("Custom Field", existing_name)
            if any(source_doc.get(key) != existing.get(key) for key in keys):
                frappe.throw(text("catalog.merge_custom_field_conflict").format(
                    field=item.fieldname, source=source, target=target), frappe.ValidationError)
            continue
        values = source_doc.as_dict()
        for key in SYSTEM_FIELDS:
            values.pop(key, None)
        values["dt"] = target
        frappe.get_doc({"doctype": "Custom Field", **values}).insert(ignore_permissions=True)
    frappe.clear_cache(doctype=target)


def _migrate_permissions(source, target):
    if not frappe.db.exists("DocType", source):
        return
    source_doc = frappe.get_doc("DocType", source)
    target_doc = frappe.get_doc("DocType", target)
    changed = False
    for permission in source_doc.permissions:
        existing = next((row for row in target_doc.permissions
                         if row.role == permission.role and row.permlevel == permission.permlevel), None)
        if existing:
            for flag in PERMISSION_FLAGS:
                if permission.get(flag) and not existing.get(flag):
                    existing.set(flag, 1)
                    changed = True
            continue
        values = {key: permission.get(key) for key in (*PERMISSION_FLAGS, "role", "permlevel", "if_owner")}
        target_doc.append("permissions", values)
        changed = True
    if changed:
        target_doc.save(ignore_permissions=True)

    available_fields = {field.fieldname for field in frappe.get_meta("Custom DocPerm").fields}
    custom_fields = [field for field in ("name", "role", "permlevel", "if_owner", *PERMISSION_FLAGS)
                     if field in available_fields]
    custom_permissions = frappe.get_all(
        "Custom DocPerm", filters={"parent": source}, fields=custom_fields, limit_page_length=0,
    )
    for permission in custom_permissions:
        existing = frappe.db.get_value(
            "Custom DocPerm", {"parent": target, "role": permission.role,
                                "permlevel": permission.permlevel}, "name",
        )
        if existing:
            current = frappe.get_doc("Custom DocPerm", existing)
            changed = False
            for flag in PERMISSION_FLAGS:
                if permission.get(flag) and not current.get(flag):
                    current.set(flag, 1)
                    changed = True
            if changed:
                current.save(ignore_permissions=True)
            continue
        values = {key: permission.get(key) for key in ("role", "permlevel", "if_owner", *PERMISSION_FLAGS)
                  if key in available_fields}
        frappe.get_doc({
            "doctype": "Custom DocPerm", "parent": target, "parenttype": "DocType",
            "parentfield": "custom_permissions", **values,
        }).insert(ignore_permissions=True)


def _migrate_property_setters(source, target):
    setters = frappe.get_all("Property Setter", filters={"doc_type": source},
                             fields=["name", "field_name", "property", "value"], limit_page_length=0)
    for setter in setters:
        existing = frappe.db.get_value("Property Setter", {
            "doc_type": target, "field_name": setter.field_name, "property": setter.property,
        }, ["name", "value"], as_dict=True)
        if existing:
            if existing.value != setter.value:
                frappe.throw(text("catalog.merge_property_conflict").format(
                    field=setter.field_name or "", source=source, target=target), frappe.ValidationError)
            frappe.delete_doc("Property Setter", setter.name, ignore_permissions=True)
        else:
            frappe.db.set_value("Property Setter", setter.name, "doc_type", target, update_modified=False)


def _copy_group(spec, row):
    target = spec["item_doctype"]
    old_name = row.name
    existing = frappe.db.exists(target, old_name)
    available = {field.fieldname for field in frappe.get_meta(target).fields}
    values = {field: value for field, value in dict(row).items()
              if field not in SYSTEM_FIELDS and field in available}
    for field in GROUP_FIELDS:
        if field in available and field not in values:
            values[field] = row.get(field)
    values.update({"record_type": spec["group_type"], spec["parent_field"]: None})
    if existing and frappe.db.get_value(target, old_name, "record_type") == spec["group_type"]:
        frappe.db.set_value(target, old_name, values, update_modified=False)
        return old_name
    name = _new_name(target) if existing else old_name
    frappe.get_doc({"doctype": target, "name": name, **values}).insert(
        ignore_permissions=True, set_name=name,
    )
    return name


def _retarget_group_links(source, target, name_map):
    if not frappe.db.exists("DocType", source):
        return
    for field_type, owner_key in (("DocField", "parent"), ("Custom Field", "dt")):
        rows = frappe.get_all(
            field_type,
            filters={"fieldtype": "Link", "options": source},
            fields=["name", owner_key, "fieldname"],
            limit_page_length=0,
        )
        for field in rows:
            owner = field.get(owner_key)
            if owner and frappe.db.exists("DocType", owner) and frappe.db.table_exists(owner):
                for row in frappe.get_all(
                    owner,
                    filters={field.fieldname: ["in", list(name_map)]},
                    fields=["name", field.fieldname],
                    limit_page_length=0,
                ):
                    replacement = name_map.get(row.get(field.fieldname))
                    if replacement:
                        frappe.db.set_value(owner, row.name, field.fieldname, replacement,
                                            update_modified=False)
            frappe.db.set_value(field_type, field.name, "options", target, update_modified=False)


def _retarget_document_references(source, target, name_map):
    references = (
        ("File", "attached_to_doctype", "attached_to_name"),
        ("Comment", "reference_doctype", "reference_name"),
        ("Communication", "reference_doctype", "reference_name"),
        ("Version", "ref_doctype", "docname"),
        ("ToDo", "reference_type", "reference_name"),
        ("Activity Log", "reference_doctype", "reference_name"),
    )
    for doctype, type_field, name_field in references:
        if not frappe.db.exists("DocType", doctype) or not frappe.db.table_exists(doctype):
            continue
        meta_fields = {field.fieldname for field in frappe.get_meta(doctype).fields}
        if type_field not in meta_fields or name_field not in meta_fields:
            continue
        rows = frappe.get_all(doctype, filters={type_field: source}, fields=["name", name_field],
                              limit_page_length=0)
        for row in rows:
            frappe.db.set_value(doctype, row.name, {
                type_field: target,
                name_field: name_map.get(row.get(name_field), row.get(name_field)),
            }, update_modified=False)


def _update_legacy_maps(spec, group_map):
    table = spec["legacy_table"]
    if not table or not frappe.db.exists("DocType", "QC Legacy Map"):
        return
    frappe.db.set_value(
        "QC Legacy Map",
        {"source_table": table, "target_doctype": spec["group_doctype"]},
        {"target_doctype": spec["item_doctype"]},
        update_modified=False,
    )
    for old_name, new_name in group_map.items():
        frappe.db.set_value(
            "QC Legacy Map",
            {"source_table": table, "target_name": old_name},
            "target_name", new_name, update_modified=False,
        )


def _mark_items_and_validate(spec, group_map):
    doctype = spec["item_doctype"]
    parent_field = spec["parent_field"]
    for row in _records(doctype, (parent_field, "record_type")):
        if row.get("record_type") == spec["group_type"]:
            continue
        old_group = row.get(parent_field)
        new_group = group_map.get(old_group, old_group)
        if new_group and not frappe.db.exists(doctype, new_group):
            frappe.throw(text("catalog.merge_missing_group").format(
                doctype=doctype, record=row.name, group=old_group or ""), frappe.ValidationError)
        if new_group and frappe.db.get_value(doctype, new_group, "record_type") != spec["group_type"]:
            frappe.throw(text("catalog.merge_missing_group").format(
                doctype=doctype, record=row.name, group=old_group or ""), frappe.ValidationError)
        frappe.db.set_value(doctype, row.name, {
            "record_type": spec["item_type"],
            parent_field: new_group,
        }, update_modified=False)


def _update_report_script():
    name = "QC Inspection Summary"
    if not frappe.db.exists("Server Script", name):
        return
    script = frappe.db.get_value("Server Script", name, "script") or ""
    old_join = "LEFT JOIN `tabQC Defect Group` qdg ON qdg.name = qd.defect_group"
    new_join = ("LEFT JOIN `tabQC Defect` qdg ON qdg.name = qd.defect_group "
                "AND qdg.record_type = 'Group'")
    if old_join in script:
        script = script.replace(old_join, new_join, 1)
        frappe.db.set_value("Server Script", name, "script", script, update_modified=False)
    elif "tabQC Defect Group" in script:
        frappe.throw(text("catalog.merge_report_script"), frappe.ValidationError)


def _update_catalog_documentation():
    name = frappe.db.get_value("API Documentation Endpoint", {"operation_id": "uqqc_bootstrap"}, "name")
    if not name:
        return
    description = frappe.db.get_value("API Documentation Endpoint", name, "description") or ""
    if "four independent UQQC DocTypes" in description or "bốn DocType UQQC riêng" in description:
        frappe.db.set_value("API Documentation Endpoint", name, "description",
                            text("docs.bootstrap_catalog", "en"), update_modified=False)


def _delete_obsolete_doctypes():
    for spec in CATALOG_MIGRATIONS:
        doctype = spec["group_doctype"]
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, ignore_permissions=True, force=True)


def execute():
    if frappe.db.exists("Patch Log", PATCH_NAME):
        return

    # Capture group rows before the metadata sync changes any old Link fields.
    groups = {
        spec["group_doctype"]: _capture_groups(spec["group_doctype"])
        for spec in CATALOG_MIGRATIONS
    }
    from factory_management.install import ensure_schema
    ensure_schema()

    group_maps = {}
    for spec in CATALOG_MIGRATIONS:
        _migrate_custom_fields(spec["group_doctype"], spec["item_doctype"])
        _migrate_permissions(spec["group_doctype"], spec["item_doctype"])
        _migrate_property_setters(spec["group_doctype"], spec["item_doctype"])
        group_map = {}
        for row in groups[spec["group_doctype"]]:
            group_map[row.name] = _copy_group(spec, row)
        group_maps[spec["group_doctype"]] = group_map
        _mark_items_and_validate(spec, group_map)
        _retarget_group_links(spec["group_doctype"], spec["item_doctype"], group_map)
        _retarget_document_references(spec["group_doctype"], spec["item_doctype"], group_map)
        _update_legacy_maps(spec, group_map)

    # Older installations may not have run the independent UQQC catalog patch.
    # Seed only a completely empty UQQC catalog; existing UQQC records stay independent.
    uqqc_had_catalog = any(
        frappe.db.count(doctype)
        for doctype in ("UQQC Defect", "UQQC Defect Position")
        if frappe.db.exists("DocType", doctype)
    )
    if not uqqc_had_catalog:
        from factory_management.patches.separate_uqqc_defects import CATALOGS, _copy_missing
        source_rows = {
            source: _records(source, fields)
            for source, _, fields in CATALOGS
        }
        _copy_missing(source_rows)

    _update_report_script()
    _update_catalog_documentation()
    for spec in CATALOG_MIGRATIONS:
        _update_legacy_maps(spec, group_maps[spec["group_doctype"]])
    frappe.clear_cache()
    _delete_obsolete_doctypes()
    frappe.clear_cache()
