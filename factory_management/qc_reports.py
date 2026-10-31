"""QC report endpoints backed by the Frappe inspection event records."""

import frappe
from frappe import _

from factory_management.api_access import require_report_access


OPERATION_ID = "qcInspectionSummaryNative"
ENTITY_TYPE = "QCInspection"
MAX_RANGE_DAYS_INCLUSIVE = 7
MAX_FILTER_LENGTH = 500

# Column expressions are fixed here; user input is always passed as a bound
# parameter. The filter behavior mirrors QCInspectionReportQueryService.
FILTERS = {
    "EventType": ("e.event_type", "contains"),
    "DeviceName": ("d.device_name", "contains"),
    "DeviceNo": ("LEFT(d.device_name, 3)", "prefix"),
    "DeviceQc": ("SUBSTRING(d.device_name, 4, 3)", "prefix"),
    "DeviceCompany": ("SUBSTRING(d.device_name, 7)", "contains"),
    "CompaniesCode": ("c.company_code", "prefix"),
    "CompaniesName": ("c.company_name", "contains"),
    "FactoriesCode": ("f.factory_code", "prefix"),
    "FactoriesName": ("f.factory_name", "contains"),
    "ProductionLinesCode": ("pl.line_code", "prefix"),
    "ProductionLinesName": ("pl.line_name", "contains"),
    "CustomersCode": ("cu.customer_code", "prefix"),
    "CustomersName": ("cu.customer_name", "contains"),
    "ProductsCode": ("p.product_code", "prefix"),
    "ProductsName": ("p.product_name", "contains"),
    "ColorsCode": ("cl.color_code", "prefix"),
    "ColorsName": ("cl.color_name", "contains"),
    "SizesCode": ("s.size_code", "prefix"),
    "SizesName": ("s.size_label", "contains"),
    "QCDefectGroupsCode": ("qdg.code", "prefix"),
    "QCDefectGroupsName": ("qdg.title", "contains"),
    "QCDefectsCode": ("qd.code", "prefix"),
    "QCDefectsName": ("qd.title", "contains"),
}


def _argument(kwargs, name):
    if name in kwargs:
        return kwargs[name]
    return frappe.form_dict.get(name)


def _report_range(raw_from, raw_to):
    if raw_from is None or raw_to is None or not str(raw_from).strip() or not str(raw_to).strip():
        frappe.throw(_("QC_REPORT_DATES_REQUIRED"), frappe.ValidationError)

    try:
        start = frappe.utils.getdate(str(raw_from).strip())
        end = frappe.utils.getdate(str(raw_to).strip())
    except (TypeError, ValueError):
        frappe.throw(_("QC_REPORT_INVALID_DATE"), frappe.ValidationError)

    if start > end:
        start, end = end, start
    if (end - start).days >= MAX_RANGE_DAYS_INCLUSIVE:
        frappe.throw(_("QC_REPORT_RANGE_TOO_LONG"), frappe.ValidationError)
    return start, end


def _date_time_text(value):
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%dT00:00:00")
    return str(value)[:10] + "T00:00:00"


@frappe.whitelist(methods=["GET"])
def inspection_summary(**kwargs):
    """Return grouped QC inspection rows using the .NET report contract."""
    require_report_access(OPERATION_ID)

    start, end = _report_range(
        _argument(kwargs, "OccurredDateFrom"),
        _argument(kwargs, "OccurredDateTo"),
    )
    params = {"date_from": start.isoformat(), "date_to": end.isoformat(),
              "entity_type_value": ENTITY_TYPE}
    conditions = []

    for name, (column, mode) in FILTERS.items():
        raw = _argument(kwargs, name)
        if raw is None or not str(raw).strip():
            continue
        value = str(raw).strip()[:MAX_FILTER_LENGTH]
        param_name = name[0].lower() + name[1:]
        params[param_name] = f"%{value}%" if mode == "contains" else f"{value}%"
        conditions.append(f"{column} LIKE %({param_name})s")

    entity_type = _argument(kwargs, "EntityType")
    if entity_type is not None and str(entity_type).strip():
        params["entity_type_filter"] = f"%{str(entity_type).strip()[:MAX_FILTER_LENGTH]}%"
        conditions.append("%(entity_type_value)s LIKE %(entity_type_filter)s")

    quantity_summary = _argument(kwargs, "QuantitySummary")
    having = ""
    if quantity_summary is not None and str(quantity_summary).strip():
        try:
            quantity_summary = int(str(quantity_summary).strip())
            if not -(2**31) <= quantity_summary <= 2**31 - 1:
                raise ValueError
        except (TypeError, ValueError):
            frappe.throw(_("QC_REPORT_INVALID_QUANTITY"), frappe.ValidationError)
        params["quantity_summary"] = quantity_summary
        having = " HAVING SUM(e.quantity_delta) = %(quantity_summary)s"

    where_extra = " AND " + " AND ".join(conditions) if conditions else ""
    query = """
SELECT
    e.event_type AS eventType,
    %(entity_type_value)s AS entityType,
    DATE(e.occurred_at) AS occurredDate,
    d.device_name AS deviceName,
    LEFT(d.device_name, 3) AS deviceNo,
    SUBSTRING(d.device_name, 4, 3) AS deviceQc,
    SUBSTRING(d.device_name, 7) AS deviceCompany,
    c.company_code AS companiesCode,
    c.company_name AS companiesName,
    f.factory_code AS factoriesCode,
    f.factory_name AS factoriesName,
    pl.line_code AS productionLinesCode,
    pl.line_name AS productionLinesName,
    COALESCE(lg.group_code, pl.line_code) AS lineGroupsCode,
    COALESCE(lg.group_name, pl.line_name) AS lineGroupsName,
    cu.customer_code AS customersCode,
    cu.customer_name AS customersName,
    p.product_code AS productsCode,
    p.product_name AS productsName,
    cl.color_code AS colorsCode,
    cl.color_name AS colorsName,
    s.size_code AS sizesCode,
    s.size_label AS sizesName,
    qdg.code AS qcDefectGroupsCode,
    qdg.title AS qcDefectGroupsName,
    qd.code AS qcDefectsCode,
    qd.title AS qcDefectsName,
    CAST(SUM(e.quantity_delta) AS SIGNED) AS quantitySummary
FROM `tabQC Inspection Event` e
INNER JOIN `tabFactory Device` d ON d.name = e.device
INNER JOIN `tabProduct` p ON p.name = e.product
INNER JOIN `tabCustomer` cu ON cu.name = p.customer
INNER JOIN `tabProduction Line` pl ON pl.name = e.line
INNER JOIN `tabFactory` f ON f.name = pl.factory
INNER JOIN `tabCompany` c ON c.name = f.company
LEFT JOIN `tabLine Group Assignment` lga ON lga.line = pl.name AND lga.is_active = 1
LEFT JOIN `tabLine Group` lg ON lg.name = lga.line_group
LEFT JOIN `tabQC Defect` qd ON qd.name = e.defect
LEFT JOIN `tabQC Defect` qdg ON qdg.name = qd.defect_group AND qdg.record_type = 'Group'
LEFT JOIN `tabProductSize` s ON s.name = e.size
LEFT JOIN `tabProduct Color` cl ON cl.name = e.color
WHERE e.occurred_at >= %(date_from)s
  AND e.occurred_at < DATE_ADD(%(date_to)s, INTERVAL 1 DAY)
""" + where_extra + """
GROUP BY e.event_type, DATE(e.occurred_at), d.device_name,
         c.company_code, c.company_name, f.factory_code, f.factory_name,
         pl.line_code, pl.line_name, lg.group_code, lg.group_name,
         cu.customer_code, cu.customer_name, p.product_code, p.product_name,
         cl.color_code, cl.color_name, s.size_code, s.size_label,
         qdg.code, qdg.title, qd.code, qd.title
""" + having + """
ORDER BY occurredDate DESC, deviceName, productsCode, productionLinesCode,
         qcDefectsCode
"""
    rows = frappe.db.sql(query, params, as_dict=True)
    for row in rows:
        row["occurredDate"] = _date_time_text(row.get("occurredDate"))
    return [dict(row) for row in rows]
