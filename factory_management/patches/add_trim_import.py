"""Provision Trim order metadata on installed sites."""


def execute():
    from factory_management.trim.provision import ensure
    ensure()
