"""Desk-editable UQQC Web Page and route-specific website context."""

from hashlib import sha256
from pathlib import Path

import frappe

from factory_management.uqqc.i18n import catalog, text


def is_page(doc):
    return (doc.get("name") or "").lower() == "uqqc" or (doc.get("route") or "").strip("/") == "uqqc"


def ensure_page():
    existing = frappe.db.get_value("Web Page", {"route": "uqqc"}, "name")
    if existing:
        if existing != "uqqc":
            frappe.throw(text("api.page_conflict"), frappe.ValidationError)
        return existing
    if frappe.db.exists("Web Page", "uqqc"):
        frappe.throw(text("api.page_conflict"), frappe.ValidationError)
    root = Path(__file__).parents[1]
    return frappe.get_doc({
        "doctype": "Web Page", "title": "UQQC", "route": "uqqc", "published": 1,
        "content_type": "HTML", "main_section_html": (root / "uqqc" / "web_page.html").read_text(encoding="utf-8"),
        "insert_style": 0, "css": "",
        "full_width": 1, "show_title": 0, "show_sidebar": 0, "enable_comments": 0,
    }).insert(ignore_permissions=True, set_name="uqqc").name


def apply_desk_style(expected_html_hash=None):
    """Explicitly replace the UQQC layout; preserve Desk edits during provisioning."""
    page = frappe.get_doc("Web Page", ensure_page())
    current_hash = sha256((page.main_section_html or "").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    if expected_html_hash and current_hash != expected_html_hash:
        frappe.throw(text("api.page_changed"), frappe.ValidationError)
    page.main_section_html = Path(__file__).with_name("web_page.html").read_text(encoding="utf-8")
    page.css = ""
    page.insert_style = 0
    page.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.clear_cache()
    return {"page": page.name, "custom_css": False}


def update_website_context(context):
    request = getattr(frappe.local, "request", None)
    if not request or request.path.rstrip("/") != "/uqqc":
        return
    context.no_cache = 1
    context.show_sidebar = False
    context.no_breadcrumbs = True
    context.full_width = True
    context.body_class = " ".join(filter(None, (context.get("body_class"), "d-block")))
    context.base_template_path = "factory_management/templates/uqqc_base.html"
    language = frappe.form_dict.get("lang") or "vi"
    context.uqqc_language = language if language in ("vi", "en") else "vi"
    context.uqqc_i18n = catalog()
    head = frappe.get_template("factory_management/templates/includes/uqqc_head.html").render(context)
    context.head_include = (context.get("head_include") or "") + head
