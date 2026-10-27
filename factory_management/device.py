"""Validation hooks for the shared device registry."""

from factory_management.device_registry import validate_device


def on_validate(doc, method=None):
    validate_device(doc, method)


