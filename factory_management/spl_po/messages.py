"""Translate SPL operator messages from Frappe CSV resources."""

import frappe


def message(code, **context):
    translated = frappe._(code)
    return translated.format(**context)
