"""Move Product Variant colors to the app-owned Product Color link."""

import frappe

from factory_management.device_registry import message


DOCTYPE = "Product Variant"
TARGET = "product_color"
RETIRED = ("qc_color", "color")


def _columns():
    if not frappe.db.table_exists(DOCTYPE, cached=False):
        return set()
    return set(frappe.db.get_table_columns(DOCTYPE))


def _rows(columns):
    selected = ["name", *(field for field in (*RETIRED, TARGET) if field in columns)]
    return frappe.db.sql(
        "SELECT " + ", ".join(f"`{field}`" for field in selected)
        + f" FROM `tab{DOCTYPE}`",
        as_dict=True,
    )


def _resolved_values(rows, columns):
    resolved = {}
    conflicts = []
    valid_colors = {}
    for row in rows:
        values = {
            row.get(field)
            for field in (*RETIRED, TARGET)
            if field in columns and row.get(field) not in (None, "")
        }
        for value in values:
            if value not in valid_colors:
                valid_colors[value] = bool(frappe.db.exists("Product Color", value))
        if len(values) > 1 or any(not valid_colors[value] for value in values):
            conflicts.append(row.name)
            continue
        resolved[row.name] = next(iter(values), None)
    if conflicts:
        frappe.throw(
            message("error.product_variant_color_conflict").format(
                count=len(conflicts), records=", ".join(conflicts[:10]),
            ),
            frappe.ValidationError,
        )
    return resolved


def prepare():
    """Validate and copy values while both legacy columns are still available."""
    if not frappe.db.exists("DocType", DOCTYPE):
        return
    columns = _columns()
    if not columns or not set(RETIRED).intersection(columns):
        return
    if frappe.db.exists("Custom Field", {"dt": DOCTYPE, "fieldname": TARGET}):
        frappe.throw(message("error.product_variant_color_schema_conflict"), frappe.ValidationError)

    rows = _rows(columns)
    resolved = _resolved_values(rows, columns)
    if TARGET not in columns:
        frappe.db.sql_ddl(f"ALTER TABLE `tab{DOCTYPE}` ADD COLUMN `{TARGET}` varchar(140) NULL")

    for name, value in resolved.items():
        if value:
            frappe.db.sql(
                f"UPDATE `tab{DOCTYPE}` SET `{TARGET}` = %s WHERE `name` = %s",
                (value, name),
            )
    copied = {
        row.name: row.product_color
        for row in frappe.db.sql(
            f"SELECT `name`, `{TARGET}` FROM `tab{DOCTYPE}`", as_dict=True,
        )
    }
    if len(copied) != len(resolved) or any(
        (copied.get(name) or None) != value for name, value in resolved.items()
    ):
        frappe.throw(message("error.product_variant_color_copy_failed"), frappe.ValidationError)


def execute():
    prepare()


def finalize():
    """Remove retired metadata and columns after the snapshot installs the target field."""
    if not frappe.db.exists("DocType", DOCTYPE):
        return
    document = frappe.get_doc("DocType", DOCTYPE)
    target = next((field for field in document.fields if field.fieldname == TARGET), None)
    if not target or target.fieldtype != "Link" or target.options != "Product Color" or any(
        field.fieldname == "color" for field in document.fields
    ):
        frappe.throw(message("error.product_variant_color_schema_conflict"), frappe.ValidationError)

    columns = _columns()
    if columns:
        if TARGET not in columns:
            frappe.throw(message("error.product_variant_color_schema_conflict"), frappe.ValidationError)
        rows = _rows(columns)
        resolved = _resolved_values(rows, columns)
        if any((row.get(TARGET) or None) != resolved[row.name] for row in rows):
            frappe.throw(message("error.product_variant_color_copy_failed"), frappe.ValidationError)

    for name in frappe.get_all(
        "Property Setter",
        filters={"doc_type": DOCTYPE, "field_name": ["in", RETIRED]},
        pluck="name",
    ):
        frappe.delete_doc("Property Setter", name, ignore_permissions=True)
    for name in frappe.get_all(
        "Custom Field",
        filters={"dt": DOCTYPE, "fieldname": "qc_color"},
        pluck="name",
    ):
        frappe.delete_doc("Custom Field", name, ignore_permissions=True)

    for field in set(RETIRED).intersection(_columns()):
        frappe.db.sql_ddl(f"ALTER TABLE `tab{DOCTYPE}` DROP COLUMN `{field}`")
    frappe.clear_cache(doctype=DOCTYPE)
