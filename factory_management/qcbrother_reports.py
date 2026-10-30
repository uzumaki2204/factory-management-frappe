"""Authenticated Frappe endpoints for the original QCBrother report contracts."""

import frappe
from frappe import _
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from factory_management.api_access import require_report_access
from factory_management.qcbrother_reporting.model import ReportInputError, ReportQuery, ReportSourceError
from factory_management.qcbrother_reporting.repository import ReportRepository
from factory_management.qcbrother_reporting.service import ReportService
from factory_management.qcbrother_reporting.sqlserver import SqlServer


class ReportValidationError(frappe.ValidationError):
    http_status_code = 400


class ReportUnavailableError(frappe.ValidationError):
    http_status_code = 503


@frappe.whitelist(methods=["GET"])
def inspection_summary(occurredOnFrom: str | None = None, occurredOnTo: str | None = None,
                       companyId: str | None = None, companyCode: str | None = None,
                       qc: str | None = None, sampleCode: str | None = None, eventNo: str | None = None):
    return _report("qcBrotherInspectionSummary", 7, occurredOnFrom, occurredOnTo,
                   companyId, companyCode, qc, sampleCode, eventNo)


@frappe.whitelist(methods=["GET"])
def inspection_aggregate(occurredOnFrom: str | None = None, occurredOnTo: str | None = None,
                         companyId: str | None = None, companyCode: str | None = None,
                         qc: str | None = None, sampleCode: str | None = None):
    return _report("qcBrotherInspectionAggregate", 31, occurredOnFrom, occurredOnTo,
                   companyId, companyCode, qc, sampleCode)


def _report(operation, max_days, begin, end, company_id, company_code, qc, sample_code, event_no=None):
    require_report_access(operation)
    config = frappe.conf.get("qcbrother_sqlserver") or {}
    try:
        if not isinstance(config, dict):
            raise ReportSourceError("QCBROTHER_SQL_CONFIG_REQUIRED")
        zone_name = config.get("time_zone") or frappe.db.get_single_value("System Settings", "time_zone")
        if zone_name is not None and not isinstance(zone_name, str):
            raise ReportSourceError("QCBROTHER_SQL_CONFIG_REQUIRED")
        zone = ZoneInfo(zone_name or "Asia/Ho_Chi_Minh")
        query = ReportQuery.parse(begin, end, zone, max_days, company_id, company_code, qc, sample_code, event_no)
        with SqlServer(config).connect() as reader:
            service = ReportService(ReportRepository(reader))
            return service.summary(query) if max_days == 7 else service.aggregate(query)
    except ReportInputError as error:
        frappe.throw(_(str(error)), ReportValidationError)
    except ZoneInfoNotFoundError:
        frappe.throw(_("QCBROTHER_SQL_CONFIG_REQUIRED"), ReportUnavailableError)
    except ReportSourceError as error:
        frappe.throw(_(str(error)), ReportUnavailableError)
