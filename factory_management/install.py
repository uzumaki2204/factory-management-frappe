"""Install and synchronize app-owned Frappe metadata."""
import json
import re
from pathlib import Path

import frappe


def field(name, label, kind="Data", options=None, **extra):
    data = {"fieldname": name, "label": label, "fieldtype": kind}
    if options:
        data["options"] = options
    data.update(extra)
    return data


MASTER_TYPES = {
    "Company": [
        field("company_name", "Company Name", reqd=1, in_list_view=1),
        field("company_code", "Company Code", reqd=1, unique=1, in_list_view=1),
        field("short_name", "Short Name"),
        field("tax_code", "Tax Code"),
        field("active", "Active", "Check", default="1"),
        field("logo_company", "Company Logo", "Attach Image"),
    ],
    "Department": [
        field("department_code", "Department Code", reqd=1, unique=1, in_list_view=1),
        field("department_name", "Department Name", reqd=1, in_list_view=1),
        field("company", "Company", "Link", "Company", reqd=1),
        field("active", "Active", "Check", default="1"),
    ],
    "Market": [
        field("code", "Market Code", in_list_view=1),
        field("name_en", "Market Name"),
        field("is_active", "Active", "Check", default="0"),
    ],
    "Product": [
        field("product_code", "Product Code", in_list_view=1),
        field("product_name", "Product Name"),
        field("season", "Season"),
        field("is_active", "Active", "Check", default="0"),
    ],
    "Color": [
        field("color_code", "Color Code", in_list_view=1),
        field("color_name", "Color Name"),
        field("is_active", "Active", "Check", default="0"),
    ],
    "ProductSize": [
        field("size_code", "Size Code", in_list_view=1),
        field("size_label", "Size Label", reqd=1),
        field("sort_order", "Sort Order", "Int"),
        field("is_active", "Active", "Check", default="0"),
    ],
    "Product Variant": [
        field("product", "Product", "Link", "Product"),
        field("market", "Market", "Link", "Market"),
        field("color", "Color", "Link", "Color"),
        field("size", "Size", "Link", "ProductSize"),
        field("is_active", "Active", "Check", default="0"),
    ],
    "Customer": [
        field("customer_code", "Customer Code", reqd=1, in_list_view=1),
        field("customer_name", "Customer Name", reqd=1, in_list_view=1),
        field("is_active", "Active", "Check", default="1"),
        field("legacy_id", "Legacy ID", read_only=1),
    ],
    "Production Season": [
        field("season_code", "Season Code", reqd=1, in_list_view=1),
        field("season_name", "Season Name", reqd=1, in_list_view=1),
        field("from_date", "From Date", "Date"),
        field("to_date", "To Date", "Date"),
        field("is_active", "Active", "Check", default="1"),
        field("legacy_id", "Legacy ID", read_only=1),
    ],
    "Factory": [
        field("factory_code", "Factory Code", reqd=1, in_list_view=1),
        field("factory_key", "Factory Key", hidden=1, read_only=1, no_copy=1),
        field("factory_name", "Factory Name", reqd=1, in_list_view=1),
        field("company", "Company", "Link", "Company", reqd=1),
        field("is_active", "Active", "Check", default="1"),
        field("legacy_id", "Legacy ID", read_only=1),
    ],
    "Line Group": [
        field("group_code", "Group Code", reqd=1, unique=1, in_list_view=1),
        field("group_name", "Group Name", reqd=1, in_list_view=1),
        field("company", "Company", "Link", "Company"),
        field("factory", "Factory", "Link", "Factory"),
        field("is_active", "Active", "Check", default="1"),
        field("legacy_id", "Legacy ID", read_only=1),
    ],
    "Production Line": [
        field("line_code", "Line Code", reqd=1, unique=1, in_list_view=1),
        field("line_name", "Line Name", reqd=1, in_list_view=1),
        field("company", "Company", "Link", "Company"),
        field("factory", "Factory", "Link", "Factory"),
        field("is_active", "Active", "Check", default="1"),
        field("legacy_id", "Legacy ID", read_only=1),
    ],
    "Line Group Assignment": [
        field("assignment_uid", "Assignment UID", reqd=1, unique=1),
        field("line", "Line", "Link", "Production Line", reqd=1, in_list_view=1),
        field("line_group", "Line Group", "Link", "Line Group", reqd=1, in_list_view=1),
        field("legacy_id", "Legacy ID", read_only=1),
        field("is_active", "Active", "Check", default="1"),
    ],
    "Product Color": [
        field("color_code", "Color Code", reqd=1, in_list_view=1),
        field("color_name", "Color Name", reqd=1, in_list_view=1),
        field("is_active", "Active", "Check", default="1"),
        field("legacy_id", "Legacy ID", read_only=1),
    ],
    "QC Defect": [
        field("record_type", "Record Type", "Select", "Group\nDefect", reqd=1, default="Defect", in_list_view=1),
        field("code", "Code", reqd=1, in_list_view=1),
        field("title", "Title", reqd=1, in_list_view=1),
        field("defect_group", "Parent Group", "Link", "QC Defect"),
        field("severity", "Severity"),
        field("is_active", "Active", "Check", default="1"),
        field("legacy_id", "Legacy ID", read_only=1),
    ],
    "QC Defect Position": [
        field("record_type", "Record Type", "Select", "Group\nPosition", reqd=1, default="Position", in_list_view=1),
        field("code", "Code", reqd=1, in_list_view=1),
        field("title", "Title", reqd=1, in_list_view=1),
        field("position_group", "Parent Group", "Link", "QC Defect Position"),
        field("is_active", "Active", "Check", default="1"),
        field("legacy_id", "Legacy ID", read_only=1),
    ],
}

# Shared factory masters are owned by KTG Master Data. The remaining entries
# are QC-specific masters and stay in Quality Control.
MASTER_TYPE_MODULES = {
    "Company": "KTG Master Data",
    "Department": "KTG Master Data",
    "Market": "KTG Master Data",
    "Product": "KTG Master Data",
    "Product Variant": "KTG Master Data",
    "Color": "KTG Master Data",
    "ProductSize": "KTG Master Data",
    "Customer": "KTG Master Data",
    "Factory": "KTG Master Data",
    "Product Color": "KTG Master Data",
    "Production Season": "KTG Master Data",
    "Line Group": "KTG Master Data",
    "Production Line": "KTG Master Data",
    "Line Group Assignment": "KTG Master Data",
}

# Keep shared master naming behavior in app metadata so it is identical on
# every site, even when the DocType already existed before an app upgrade.
DOCTYPE_SETTINGS = {
    "Customer": {"autoname": "hash", "allow_rename": 1},
    "Factory": {
        "naming_rule": "By fieldname",
        "autoname": "field:factory_key",
        "allow_rename": 1,
    },
    "Product Color": {"naming_rule": "By fieldname", "autoname": "field:color_code", "allow_rename": 1},
    "Production Season": {"naming_rule": "By fieldname", "autoname": "field:season_code", "allow_rename": 1},
    "QC Defect": {"naming_rule": "By fieldname", "autoname": "field:code", "allow_rename": 1},
    "ProductSize": {"naming_rule": "By fieldname", "autoname": "field:size_label", "allow_rename": 1},
    "Line Group": {"naming_rule": "By fieldname", "autoname": "field:group_code", "allow_rename": 1},
    "Market": {"naming_rule": "By fieldname", "autoname": "field:code", "allow_rename": 1},
    "Production Line": {"naming_rule": "By fieldname", "autoname": "field:line_code", "allow_rename": 1},
}

# Connections is a derived Desk view; its source is the DocType fields and links.
DOCTYPE_CHILD_TABLES = ("fields", "permissions", "actions", "links", "states")
DOCTYPE_SYSTEM_FIELDS = {
    "owner", "creation", "modified", "modified_by", "docstatus", "idx",
    "_user_tags", "_comments", "_assign", "_liked_by", "_seen",
}
CHILD_SYSTEM_FIELDS = DOCTYPE_SYSTEM_FIELDS | {"name", "parent", "parenttype", "parentfield"}
METADATA_DIRECTORY = Path(__file__).parent / "doctype_metadata"

DOCUMENTATION_TYPES = {
    "API Documentation Service": [
        field("service_key", "Service Key", reqd=1, unique=1, in_list_view=1),
        field("service_title", "Service Title", reqd=1, in_list_view=1),
        field("version", "Version", default="1.0.0"),
        field("description", "Description", "Small Text"),
        field("is_active", "Active", "Check", default="1"),
    ],
    "API Documentation Endpoint": [
        field("service", "Service", "Link", "API Documentation Service", reqd=1, in_list_view=1),
        field("operation_id", "Operation ID", reqd=1, unique=1, in_list_view=1),
        field("path", "Path", reqd=1, in_list_view=1),
        field("http_method", "HTTP Method", "Select", "GET\nPOST\nPUT\nPATCH\nDELETE", reqd=1, in_list_view=1),
        field("summary", "Summary", reqd=1),
        field("description", "Description", "Small Text"),
        field("tags_json", "Tags JSON", "Code", "JSON"),
        field("parameters_json", "Parameters JSON", "Code", "JSON"),
        field("request_body_json", "Request Body JSON", "Code", "JSON"),
        field("responses_json", "Responses JSON", "Code", "JSON", reqd=1),
        field("security_json", "Security JSON", "Code", "JSON"),
        field("is_active", "Active", "Check", default="1"),
    ],
    "API Documentation Endpoint Role": [
        field("role", "Role", "Link", "Role", reqd=1, in_list_view=1),
    ],
}

TRANSACTION_TYPES = {
    "QC Legacy Map": [
        field("mapping_uid", "Mapping UID", reqd=1, unique=1),
        field("source_table", "Source Table", reqd=1, in_list_view=1),
        field("legacy_id", "Legacy ID", reqd=1, in_list_view=1),
        field("target_doctype", "Target DocType", reqd=1),
        field("target_name", "Target Name", reqd=1),
    ],
    "QC Inspection Event": [
        field("event_uid", "Event UID", reqd=1, unique=1),
        field("local_event_id", "Local Event ID", reqd=1),
        field("device", "Device", "Link", "Factory Device", reqd=1, in_list_view=1),
        field("event_type", "Event Type", reqd=1, in_list_view=1),
        field("product", "Product", "Link", "Product", in_list_view=1),
        field("line", "Line", "Link", "Production Line"),
        field("color", "Color", "Link", "Product Color"),
        field("size", "Size", "Link", "ProductSize"),
        field("defect", "Defect", "Link", "QC Defect"),
        field("quantity_delta", "Quantity Delta", "Int"),
        field("occurred_at", "Occurred At", "Datetime", reqd=1, in_list_view=1),
        field("synced_at", "Synced At", "Datetime"),
        field("server_date_key", "Server Date Key"),
    ],
    "QC Favorite": [
        field("favorite_uid", "Favorite UID", reqd=1, unique=1),
        field("device", "Device", "Link", "Factory Device", reqd=1, in_list_view=1),
        field("defect", "Defect", "Link", "QC Defect", reqd=1, in_list_view=1),
    ],
}

DEVICE_TYPES = {
    "Factory Data Epoch": [
        field("generation", "Generation", reqd=1, unique=1),
        field("reset_at_utc", "Reset At UTC", "Datetime", reqd=1),
    ],
    "Factory Device": [
        field("device_id", "Device ID", reqd=1, unique=1, in_list_view=1),
        field("device_uid", "Device UID", reqd=1, unique=1, in_list_view=1),
        field("device_name", "Device Name", in_list_view=1),
        field("status", "Status", "Select", "Pending\nApproved\nRejected\nDeactivated", default="Pending", in_list_view=1),
        field("is_active", "Active", "Check", default="1"),
        field("company", "Company", "Link", "Company"),
        field("factory", "Factory", "Link", "Factory"),
        field("line", "Line", "Link", "Production Line"),
        field("client_lock_enabled", "Client Lock Enabled", "Check", default="1"),
        field("last_seen_at", "Last Seen", "Datetime"),
    ],
    "Factory Device Client": [
        field("device", "Device", "Link", "Factory Device", reqd=1, in_list_view=1),
        field("service_key", "Service Key", reqd=1, in_list_view=1),
        field("status", "Status", "Select", "Pending\nApproved\nRejected\nRevoked", default="Pending", reqd=1, in_list_view=1),
        field("token_hash", "Token Hash", unique=1, hidden=1, read_only=1, no_copy=1),
        field("browser_name", "Browser Name", in_list_view=1),
        field("operating_system", "Operating System", in_list_view=1),
        field("last_seen_at", "Last Seen", "Datetime"),
    ],
}


def ensure_module():
    for module_name in ("Factory Management", "Quality Control", "API Management", "KTG Master Data", "UQQC"):
        owner = frappe.db.get_value("Module Def", module_name, "app_name")
        if module_name == "Factory Management" and owner and owner != "factory_management":
            from factory_management.device_registry import message
            frappe.throw(message("error.namespace_conflict"), frappe.ValidationError)
        if module_name == "KTG Master Data" and owner and owner != "factory_management":
            from factory_management.device_registry import message
            frappe.throw(message("error.master_data_module_conflict"), frappe.ValidationError)
        if not frappe.db.exists("Module Def", module_name):
            frappe.get_doc({
                "doctype": "Module Def",
                "module_name": module_name,
                "app_name": "factory_management",
            }).insert(ignore_permissions=True)


def _metadata_filename(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") + ".json"


def _clean_metadata_value(value, child=False):
    if isinstance(value, dict):
        ignored = CHILD_SYSTEM_FIELDS if child else DOCTYPE_SYSTEM_FIELDS
        return {
            key: _clean_metadata_value(item, child=child)
            for key, item in value.items()
            if key not in ignored and not key.startswith("_") and item is not None
        }
    if isinstance(value, list):
        return [_clean_metadata_value(item, child=child) for item in value]
    return value


def _load_doctype_snapshot(name):
    path = METADATA_DIRECTORY / _metadata_filename(name)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _doctype_definition(name, fields, module, is_child):
    data = {
        "doctype": "DocType",
        "name": name,
        "module": module,
        "custom": 1,
        "autoname": "field:device_id" if name == "Factory Device" else "hash",
        "issingle": 0,
        "istable": 1 if is_child else 0,
        "track_changes": 1,
        "fields": fields,
        "permissions": [] if is_child else [{
            "role": "System Manager",
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 1,
            "report": 1,
        }],
        "actions": [],
        "links": [],
        "states": [],
    }
    data.update(DOCTYPE_SETTINGS.get(name, {}))
    return data


def _ensure_snapshot_doctype_shells():
    """Create empty app-owned DocTypes before syncing fields and custom fields.

    Metadata snapshots can contain Link fields whose target DocType appears later
    in the installation order (or points back to the current DocType). Frappe
    validates those targets immediately, so make every snapshot-backed DocType
    available first, then let the normal schema pass apply its complete metadata.
    """
    for path in sorted(METADATA_DIRECTORY.glob("*.json")):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        data = snapshot.get("doctype") or {}
        name = data.get("name")
        if not name or not data.get("custom") or frappe.db.exists("DocType", name):
            continue

        shell = _doctype_definition(
            name,
            [],
            data.get("module") or "Factory Management",
            bool(data.get("istable")),
        )
        # A shell has no user fields yet, so use an autoname mode that does not
        # depend on a field being installed in the later metadata sync.
        shell["autoname"] = "hash"
        frappe.get_doc(shell).insert(ignore_permissions=True)


def _metadata_document_data(document):
    data = _clean_metadata_value(document.as_dict())
    data["doctype"] = document.doctype
    data["name"] = document.name
    for table in DOCTYPE_CHILD_TABLES:
        if table in data:
            data[table] = [_clean_metadata_value(row, child=True) for row in data[table]]
    return data


def _sync_snapshot_records(doctype, records, *, create_only=False):
    for record in records:
        name = record.get("name")
        if not name:
            continue
        values = {key: value for key, value in record.items() if key not in {"doctype", "name"}}
        existing_name = name if frappe.db.exists(doctype, name) else None
        if not existing_name and doctype == "Custom Field":
            # Custom Field names can differ between sites even when the field is
            # the same. Frappe identifies a field by DocType + fieldname.
            identity = {key: record.get(key) for key in ("dt", "fieldname")}
            if all(identity.values()):
                existing_name = frappe.db.get_value(doctype, identity, "name")

        if existing_name:
            if create_only:
                continue
            document = frappe.get_doc(doctype, existing_name)
            changed = any(
                _clean_metadata_value(document.get(key)) != _clean_metadata_value(value)
                for key, value in values.items()
            )
            if changed:
                document.update(values)
                document.save(ignore_permissions=True)
        else:
            frappe.get_doc({"doctype": doctype, "name": name, **values}).insert(ignore_permissions=True)


def _apply_doctype_snapshot(name, snapshot):
    data = snapshot["doctype"]
    _sync_snapshot_records("Role", snapshot.get("roles", []), create_only=True)

    if data.get("custom"):
        if not frappe.db.exists("DocType", name):
            frappe.get_doc(data).insert(ignore_permissions=True)
        else:
            document = frappe.get_doc("DocType", name)
            changed = False
            for key, value in data.items():
                if key in {"doctype", "name"}:
                    continue
                desired = [_clean_metadata_value(row, child=True) for row in value] if key in DOCTYPE_CHILD_TABLES else value
                current = [_clean_metadata_value(row, child=True) for row in document.get(key)] if key in DOCTYPE_CHILD_TABLES else document.get(key)
                if _clean_metadata_value(current) != _clean_metadata_value(desired):
                    document.set(key, desired)
                    changed = True
            if changed:
                document.save(ignore_permissions=True)
    elif not frappe.db.exists("DocType", name):
        from factory_management.device_registry import message
        frappe.throw(
            message("error.standard_doctype_missing").format(doctype=name),
            frappe.ValidationError,
        )

    _sync_snapshot_records("Custom Field", snapshot.get("custom_fields", []))
    _sync_snapshot_records("Property Setter", snapshot.get("property_setters", []))
    _sync_snapshot_records("Custom DocPerm", snapshot.get("custom_permissions", []))
    _sync_snapshot_records("DocType Link", snapshot.get("custom_links", []))
    _sync_snapshot_records("DocType Action", snapshot.get("custom_actions", []))


def ensure_doctype(name, fields, module="Quality Control", is_child=False):
    snapshot = _load_doctype_snapshot(name)
    if snapshot:
        _apply_doctype_snapshot(name, snapshot)
        return

    settings = {"module": module, **DOCTYPE_SETTINGS.get(name, {})}
    if frappe.db.exists("DocType", name):
        # On the first upgrade, keep the existing Desk definition intact. Export it
        # with export_doctype_metadata() before publishing a snapshot-backed release.
        current = frappe.db.get_value("DocType", name, list(settings), as_dict=True)
        updates = {key: value for key, value in settings.items() if current.get(key) != value}
        if updates:
            frappe.db.set_value("DocType", name, updates, update_modified=False)
        return

    frappe.get_doc(_doctype_definition(name, fields, module, is_child)).insert(ignore_permissions=True)


def export_doctype_metadata():
    """Export current app-managed DocType metadata for source-controlled releases."""
    from factory_management.uqqc.provision import CATALOG_TYPES

    names = (
        *MASTER_TYPES,
        *DEVICE_TYPES,
        *TRANSACTION_TYPES,
        *DOCUMENTATION_TYPES,
        *CATALOG_TYPES,
        "UQQC Inspection Event",
    )
    METADATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    exported = []
    for name in names:
        if not frappe.db.exists("DocType", name):
            continue
        document = frappe.get_doc("DocType", name)
        snapshot = {
            "doctype": _metadata_document_data(document),
            "custom_fields": [],
            "property_setters": [],
            "custom_permissions": [],
            "custom_links": [],
            "custom_actions": [],
            "roles": [],
        }
        for child_doctype, filters, target in (
            ("Custom Field", {"dt": name}, "custom_fields"),
            ("Property Setter", {"doc_type": name}, "property_setters"),
            ("Custom DocPerm", {"parent": name}, "custom_permissions"),
            ("DocType Link", {"parent": name, "custom": 1}, "custom_links"),
            ("DocType Action", {"parent": name, "custom": 1}, "custom_actions"),
        ):
            records = frappe.get_all(child_doctype, filters=filters, fields=["name"], order_by="name asc")
            snapshot[target] = [
                _metadata_document_data(frappe.get_doc(child_doctype, row.name))
                for row in records
            ]
        role_names = {
            row.role for row in document.permissions if row.role
        } | {
            row.get("role") for row in snapshot["custom_permissions"] if row.get("role")
        }
        snapshot["roles"] = [
            _metadata_document_data(frappe.get_doc("Role", role_name))
            for role_name in sorted(role_names)
            if frappe.db.exists("Role", role_name)
        ]
        path = METADATA_DIRECTORY / _metadata_filename(name)
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        exported.append(path.name)
    return exported


def ensure_report_reader_role():
    from factory_management.api_access import READER_ROLE

    if not frappe.db.exists("Role", READER_ROLE):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": READER_ROLE,
            "desk_access": 0,
        }).insert(ignore_permissions=True)


def ensure_custom_field(dt, name, label, kind="Data", options=None):
    if not frappe.db.exists("Custom Field", {"dt": dt, "fieldname": name}):
        data = {"doctype": "Custom Field", "dt": dt, "fieldname": name,
                "label": label, "fieldtype": kind}
        if options:
            data["options"] = options
        frappe.get_doc(data).insert(ignore_permissions=True)


def ensure_schema():
    ensure_module()
    _ensure_snapshot_doctype_shells()
    for name, fields in MASTER_TYPES.items():
        ensure_doctype(name, fields, module=MASTER_TYPE_MODULES.get(name, "Quality Control"))
    ensure_device_schema()
    for name, fields in TRANSACTION_TYPES.items():
        ensure_doctype(name, fields, module=MASTER_TYPE_MODULES.get(name, "Quality Control"))
    for name, fields in DOCUMENTATION_TYPES.items():
        ensure_doctype(name, fields, "API Management", is_child=name == "API Documentation Endpoint Role")
    ensure_report_reader_role()
    ensure_custom_field("API Documentation Service", "base_url", "Base URL")
    ensure_custom_field("API Documentation Service", "openapi_url", "OpenAPI URL")
    ensure_custom_field("API Documentation Endpoint", "allowed_roles", "Allowed Roles", "Table", "API Documentation Endpoint Role")
    ensure_custom_field("Product", "customer", "Customer", "Link", "Customer")
    ensure_custom_field("Product", "production_season", "Production Season", "Link", "Production Season")
    ensure_custom_field("Product Variant", "qc_color", "QC Color", "Link", "Product Color")
    from factory_management.api_docs import ensure_catalog
    ensure_catalog()
    from factory_management.qc_web_page import ensure_qc_web_page, ensure_qc_web_page_permissions
    ensure_qc_web_page_permissions()
    ensure_qc_web_page()
    from factory_management.uqqc.provision import ensure as ensure_uqqc
    ensure_uqqc()
    frappe.clear_cache()


def ensure_device_schema():
    ensure_module()
    for name, fields in DEVICE_TYPES.items():
        owner = frappe.db.get_value("DocType", name, "module")
        if owner and owner != "Factory Management":
            from factory_management.device_registry import message
            frappe.throw(message("error.namespace_conflict"), frappe.ValidationError)
        ensure_doctype(name, fields, "Factory Management")


def after_install():
    ensure_schema()
