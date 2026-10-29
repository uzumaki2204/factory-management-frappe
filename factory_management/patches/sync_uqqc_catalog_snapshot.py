"""Sync UQQC catalog metadata snapshots during Pilot-managed app updates."""


def execute():
    """Ensure snapshot-only field changes are applied during the migrate step."""
    from factory_management.uqqc.provision import ensure_schema

    ensure_schema()
