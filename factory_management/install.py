"""Additive QC schema for the Factory Management Frappe app."""
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
    "Size": [
        field("size_code", "Size Code", in_list_view=1),
        field("size_label", "Size Name"),
        field("sort_order", "Sort Order", "Int"),
        field("is_active", "Active", "Check", default="0"),
    ],
    "Product Variant": [
        field("product", "Product", "Link", "Product"),
        field("market", "Market", "Link", "Market"),
        field("color", "Color", "Link", "Color"),
        field("size", "Size", "Link", "Size"),
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
        field("factory_name", "Factory Name", reqd=1, in_list_view=1),
        field("company", "Company", "Link", "Company"),
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
        field("line_code", "Line Code", reqd=1, in_list_view=1),
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
    "QC Defect Group": [
        field("code", "Code", reqd=1, in_list_view=1),
        field("title", "Title", reqd=1, in_list_view=1),
        field("is_active", "Active", "Check", default="1"),
        field("legacy_id", "Legacy ID", read_only=1),
    ],
    "QC Defect": [
        field("code", "Code", reqd=1, in_list_view=1),
        field("title", "Title", reqd=1, in_list_view=1),
        field("defect_group", "Defect Group", "Link", "QC Defect Group", reqd=1),
        field("severity", "Severity"),
        field("is_active", "Active", "Check", default="1"),
        field("legacy_id", "Legacy ID", read_only=1),
    ],
    "QC Defect Position Group": [
        field("code", "Code", reqd=1, in_list_view=1),
        field("title", "Title", reqd=1, in_list_view=1),
        field("is_active", "Active", "Check", default="1"),
        field("legacy_id", "Legacy ID", read_only=1),
    ],
    "QC Defect Position": [
        field("code", "Code", reqd=1, in_list_view=1),
        field("title", "Title", reqd=1, in_list_view=1),
        field("position_group", "Position Group", "Link", "QC Defect Position Group", reqd=1),
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
    "Size": "KTG Master Data",
    "Customer": "KTG Master Data",
}

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
        field("event_key", "Event Key"),
        field("entity_type", "Entity Type"),
        field("entity_id", "Entity ID"),
        field("product", "Product", "Link", "Product", in_list_view=1),
        field("line", "Line", "Link", "Production Line"),
        field("color", "Color", "Link", "Product Color"),
        field("size", "Size", "Link", "Size"),
        field("defect", "Defect", "Link", "QC Defect"),
        field("quantity_delta", "Quantity Delta", "Int"),
        field("payload_json", "Payload", "Code", "JSON"),
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
        field("browser_name", "Browser Name"),
        field("operating_system", "Operating System"),
        field("last_seen_at", "Last Seen", "Datetime"),
    ],
    "Factory Device Access": [
        field("access_key", "Access Key", reqd=1, unique=1, read_only=1, hidden=1),
        field("device", "Device", "Link", "Factory Device", reqd=1, in_list_view=1),
        field("service_key", "Service Key", reqd=1, in_list_view=1),
        field("is_enabled", "Enabled", "Check", default="0", in_list_view=1),
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
    for module_name in ("Factory Management", "Quality Control", "API Management", "KTG Master Data"):
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


def ensure_doctype(name, fields, module="Quality Control", is_child=False):
    if frappe.db.exists("DocType", name):
        if frappe.db.get_value("DocType", name, "module") != module:
            frappe.db.set_value("DocType", name, "module", module)
        return
    frappe.get_doc({
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
    }).insert(ignore_permissions=True)


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
    for name, fields in MASTER_TYPES.items():
        ensure_doctype(name, fields, module=MASTER_TYPE_MODULES.get(name, "Quality Control"))
    ensure_device_schema()
    for name, fields in TRANSACTION_TYPES.items():
        ensure_doctype(name, fields)
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
