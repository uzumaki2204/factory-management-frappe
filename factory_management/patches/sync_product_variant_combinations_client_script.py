"""Install the Product variant display as an app-managed Client Script."""

from pathlib import Path

import frappe


DOCTYPE = "Product"
SCRIPT_NAME = "Factory Management Product Variant Combinations"
SCRIPT_PATH = Path(__file__).resolve().parents[1] / "public" / "js" / "product_variant_combinations.js"


def execute():
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    values = {
        "dt": DOCTYPE,
        "view": "Form",
        "enabled": 1,
        "script": script,
    }

    if frappe.db.exists("Client Script", SCRIPT_NAME):
        document = frappe.get_doc("Client Script", SCRIPT_NAME)
        changed = any(document.get(key) != value for key, value in values.items())
        if changed:
            document.update(values)
            document.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": SCRIPT_NAME,
            **values,
        }).insert(ignore_permissions=True)

    frappe.clear_cache(doctype=DOCTYPE)
