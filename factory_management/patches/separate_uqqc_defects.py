"""Compatibility utilities for the merged, independent UQQC catalogs."""

import frappe


PATCH_NAME = "factory_management.patches.separate_uqqc_defects"
CATALOGS = (
    ("QC Defect", "UQQC Defect", (
        "record_type", "code", "title", "defect_group", "severity", "is_active", "legacy_id",
    )),
    ("QC Defect Position", "UQQC Defect Position", (
        "record_type", "code", "title", "position_group", "is_active", "legacy_id",
    )),
)


def _copy_missing(rows):
    """Copy QC catalog records to the independent UQQC catalog, parents first."""
    for source, target, fields in CATALOGS:
        records = sorted(
            rows.get(source, []),
            key=lambda row: (row.get("record_type") != "Group", row.get("name") or ""),
        )
        for row in records:
            if frappe.db.exists(target, row.name):
                continue
            frappe.get_doc({
                "doctype": target,
                "name": row.name,
                **{field: row.get(field) for field in fields},
            }).insert(ignore_permissions=True, set_name=row.name)


def execute():
    """Leave legacy catalog migration to merge_defect_catalogs, which runs next."""
    return
