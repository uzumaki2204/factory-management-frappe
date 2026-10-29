"""Install SPL PO metadata and scheduler on Pilot-managed upgrades."""


def execute():
    from factory_management.spl_po.provision import ensure
    ensure()
