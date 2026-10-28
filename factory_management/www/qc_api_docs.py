"""Swagger UI for API contracts managed in Frappe Desk."""

import frappe


def get_context(context):
    frappe.only_for("System Manager")
    context.no_cache = 1
    context.show_sidebar = False
    context.title = frappe._("API Documentation")
