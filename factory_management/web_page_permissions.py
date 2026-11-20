"""Compose route-specific permissions without expanding access to other pages."""

import frappe

from factory_management import qc_web_page
from factory_management.uqqc.web_page import is_page


def has_permission(doc, ptype=None, user=None, **kwargs):
    if is_page(doc):
        user = user or frappe.session.user
        return (user == "Administrator" or ptype not in qc_web_page._EDIT_PERMISSIONS
                or "System Manager" in frappe.get_roles(user))
    return qc_web_page.has_web_page_permission(doc, ptype=ptype, user=user, **kwargs)


def query_conditions(user=None, **kwargs):
    conditions = qc_web_page.web_page_query_conditions(user=user, **kwargs)
    if not conditions:
        return ""
    return "(" + conditions + " OR `tabWeb Page`.`name` = 'uqqc' OR `tabWeb Page`.`route` = 'uqqc')"
