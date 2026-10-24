"""Provision and protect the Desk-managed QC Web Page."""

from pathlib import Path

import frappe
import frappe.permissions
from frappe import _


QC_ROUTE = "qc"
QC_PAGE_NAME = "qc"
_EDIT_PERMISSIONS = {"create", "write", "delete", "share", "import", "export", "print", "email"}


def ensure_qc_web_page():
    """Seed the Web Page once; future Desk edits remain authoritative."""
    existing = frappe.db.get_value("Web Page", {"route": QC_ROUTE}, "name")
    if existing:
        return existing

    if frappe.db.exists("Web Page", QC_PAGE_NAME):
        frappe.throw(_("QC_WEB_PAGE_NAME_CONFLICT"), frappe.ValidationError)

    root = Path(__file__).parent
    page = frappe.get_doc({
        "doctype": "Web Page",
        "title": "QC",
        "route": QC_ROUTE,
        "published": 1,
        "content_type": "HTML",
        "main_section_html": (root / "web_pages" / "qc.html").read_text(encoding="utf-8"),
        "insert_style": 1,
        "css": (root / "public" / "css" / "qc-primary.css").read_text(encoding="utf-8"),
        "full_width": 1,
        "show_title": 0,
        "show_sidebar": 0,
        "enable_comments": 0,
    })
    page.insert(ignore_permissions=True)
    return page.name


def ensure_qc_web_page_permissions():
    """Let System Managers open the Web Page form without changing other pages' access."""
    frappe.permissions.setup_custom_perms("Web Page")
    filters = {"parent": "Web Page", "role": "System Manager", "permlevel": 0, "if_owner": 0}
    name = frappe.db.get_value("Custom DocPerm", filters, "name")
    if name:
        row = frappe.get_doc("Custom DocPerm", name)
        changed = False
        for field in ("read", "write", "create", "delete"):
            if not row.get(field):
                row.set(field, 1)
                changed = True
        if changed:
            row.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": "Custom DocPerm",
            "parent": "Web Page",
            "parenttype": "DocType",
            "parentfield": "permissions",
            "role": "System Manager",
            "permlevel": 0,
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 1,
        }).insert(ignore_permissions=True)
    frappe.clear_cache(doctype="Web Page")


def update_website_context(context):
    request = getattr(frappe.local, "request", None)
    if not request or request.path.rstrip("/") != "/qc":
        return

    context.no_cache = 1
    context.show_sidebar = False
    context.no_breadcrumbs = True
    context.full_width = True
    context.body_class = " ".join(filter(None, (context.get("body_class"), "qc-web-page")))
    context.base_template_path = "factory_management/templates/qc_base.html"
    head = frappe.get_template("factory_management/templates/includes/qc_head.html").render(context)
    context.head_include = (context.get("head_include") or "") + head


def _is_qc_page(doc):
    return (doc.get("name") or "").lower() == QC_PAGE_NAME or (doc.get("route") or "").strip("/") == QC_ROUTE


def _has_other_page_role_permission(user, ptype):
    roles = set(frappe.get_roles(user)) - {"System Manager"}
    permission = "read" if ptype in (None, "select") else ptype
    return any(
        row.role in roles and row.get(permission)
        for row in frappe.get_meta("Web Page").permissions
    )


def has_web_page_permission(doc, ptype=None, user=None, **_kwargs):
    """Only System Managers may change QC; existing roles govern other pages."""
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    roles = set(frappe.get_roles(user))
    if _is_qc_page(doc):
        return ptype not in _EDIT_PERMISSIONS or "System Manager" in roles
    if "System Manager" in roles:
        return _has_other_page_role_permission(user, ptype)
    return True


def web_page_query_conditions(user=None, **_kwargs):
    user = user or frappe.session.user
    if user == "Administrator" or "System Manager" not in frappe.get_roles(user):
        return ""
    if _has_other_page_role_permission(user, "read"):
        return ""
    return "(`tabWeb Page`.`name` = 'qc' OR `tabWeb Page`.`route` = 'qc')"
