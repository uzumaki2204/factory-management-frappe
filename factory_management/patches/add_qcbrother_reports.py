"""Make Pilot run migrate and provision the two QCBrother catalog records."""


def execute():
    from factory_management.api_docs import ensure_catalog

    ensure_catalog()
