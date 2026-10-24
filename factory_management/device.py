"""Validation hooks for the shared device registry."""

from factory_management.device_registry import validate_access, validate_device


def on_validate(doc, method=None):
    validate_device(doc, method)


def on_access_validate(doc, method=None):
    validate_access(doc, method)
