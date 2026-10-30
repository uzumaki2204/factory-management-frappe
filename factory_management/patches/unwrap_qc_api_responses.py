"""Expose direct JSON success schemas for existing QC/UQQC operations."""


def execute():
    from factory_management.api_contracts import migrate_success_contracts

    migrate_success_contracts()
