"""Refresh the Product form script with grouped variant display logic."""

from factory_management.patches.sync_product_variant_combinations_client_script import execute as sync_client_script


def execute():
    sync_client_script()
