"""Translate SPL operator messages from Frappe CSV resources."""

import frappe


def message(message_key, **context):
    translated = frappe._(message_key)
    return translated.format(**context)
