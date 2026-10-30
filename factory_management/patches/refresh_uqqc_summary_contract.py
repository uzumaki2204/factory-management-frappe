"""Update the existing InspectionSummary contract for its UQQC source."""


def execute():
    from factory_management.qcbrother_reporting.catalog import refresh_summary_contract

    refresh_summary_contract()
