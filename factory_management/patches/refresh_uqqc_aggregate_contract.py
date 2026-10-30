"""Update the existing InspectionAggregate contract for its Frappe source."""


def execute():
    from factory_management.qcbrother_reporting.catalog import refresh_aggregate_contract

    refresh_aggregate_contract()
