"""Permission-independent UQQC report filter options and multi-value query runner."""

import json

import frappe
from frappe import _


REPORT_ROLES = {"QC Report Reader", "System Manager"}
FILTER_FIELDS_BY_TYPE = {
    "summary": ("qc", "company", "product"),
    "device": ("qc", "company", "product", "device", "market", "color", "size"),
}

# Match the UTC+7 day boundaries and QC1/QC2 extraction used by UQQC Query Reports.
QC_EXPR = (
    "CASE "
    "WHEN LOCATE('QC1', UPPER(device.device_name)) > 0 "
    "AND (LOCATE('QC2', UPPER(device.device_name)) = 0 "
    "OR LOCATE('QC1', UPPER(device.device_name)) < LOCATE('QC2', UPPER(device.device_name))) THEN 'QC1' "
    "WHEN LOCATE('QC2', UPPER(device.device_name)) > 0 THEN 'QC2' "
    "ELSE '' END"
)

BASE_FROM = (
    "FROM `tabUQQC Inspection Event` e "
    "JOIN `tabFactory Device` device ON device.name = e.device "
    "JOIN `tabProduction Line` line ON line.name = e.line AND line.company = device.company "
    "JOIN `tabCompany` company ON company.name = line.company "
    "JOIN `tabProduct` product ON product.name = e.product"
)

DEVICE_JOINS = (
    " JOIN `tabMarket` market ON market.name = e.market"
    " JOIN `tabProduct Color` color ON color.name = e.color"
    " JOIN `tabProductSize` size ON size.name = e.size"
)

DATE_RANGE_WHERE = (
    "e.occurred_at >= DATE_SUB(CONCAT(%(from_date)s, ' 00:00:00'), INTERVAL 7 HOUR) "
    "AND e.occurred_at < DATE_SUB(DATE_ADD(CONCAT(%(to_date)s, ' 00:00:00'), INTERVAL 1 DAY), INTERVAL 7 HOUR)"
)

FILTER_COLUMN_MAP = {
    "company": "company.name",
    "product": "product.name",
    "device": "e.device",
    "market": "e.market",
    "color": "e.color",
    "size": "e.size",
}

SUMMARY_COLUMNS = [
    {"fieldname": "occurredOn", "label": "Ngày", "fieldtype": "Date", "width": 100},
    {"fieldname": "deviceQc", "label": "QC", "fieldtype": "Data", "width": 70},
    {"fieldname": "companyName", "label": "Công ty", "fieldtype": "Data", "width": 150},
    {"fieldname": "sampleCode", "label": "Mã hàng", "fieldtype": "Data", "width": 120},
    {"fieldname": "pass", "label": "Số lượng đạt", "fieldtype": "Int", "width": 110},
    {"fieldname": "rework", "label": "Số lượng tái sửa", "fieldtype": "Int", "width": 120},
    {"fieldname": "defect", "label": "Số lượng lỗi", "fieldtype": "Int", "width": 100},
    {"fieldname": "inspected", "label": "Tổng kiểm", "fieldtype": "Int", "width": 100},
    {"fieldname": "defectRate", "label": "Tỷ lệ lỗi", "fieldtype": "Percent", "width": 100},
    {"fieldname": "totalRework", "label": "Lũy kế tái sửa", "fieldtype": "Int", "width": 120},
    {"fieldname": "totalPass", "label": "Lũy kế đạt", "fieldtype": "Int", "width": 110},
    {"fieldname": "totalDefect", "label": "Lũy kế lỗi", "fieldtype": "Int", "width": 100},
    {"fieldname": "totalInspected", "label": "Lũy kế kiểm", "fieldtype": "Int", "width": 110},
    {"fieldname": "totalDefectRate", "label": "Tỷ lệ lũy kế", "fieldtype": "Percent", "width": 120},
]

DEVICE_COLUMNS = [
    {"fieldname": "companyName", "label": "Công ty", "fieldtype": "Data", "width": 150},
    {"fieldname": "occurredOn", "label": "Ngày", "fieldtype": "Date", "width": 100},
    {"fieldname": "deviceQc", "label": "QC", "fieldtype": "Data", "width": 70},
    {"fieldname": "deviceName", "label": "Mã máy", "fieldtype": "Data", "width": 130},
    {"fieldname": "sampleCode", "label": "Mã hàng", "fieldtype": "Data", "width": 120},
    {"fieldname": "marketName", "label": "Thị trường", "fieldtype": "Data", "width": 100},
    {"fieldname": "colorCode", "label": "Màu", "fieldtype": "Data", "width": 80},
    {"fieldname": "sizeLabel", "label": "Size", "fieldtype": "Data", "width": 80},
    {"fieldname": "pass", "label": "Đạt", "fieldtype": "Int", "width": 90},
    {"fieldname": "rework", "label": "Tái sửa", "fieldtype": "Int", "width": 100},
    {"fieldname": "defect", "label": "Lỗi", "fieldtype": "Int", "width": 90},
]


@frappe.whitelist(methods=["GET", "POST"])
def get_filter_options(report_type: str = "summary"):
    """Return distinct report filter combinations regardless of date or master Link permissions."""
    _require_report_access()
    kind = _normalize_report_type(report_type)
    # Query SQL directly so master DocType permissions and User Permissions do not hide report options.
    rows = _query_filter_rows(kind)
    return {"rows": rows}


@frappe.whitelist(methods=["GET", "POST"])
def run_report(
    from_date: str | None = None,
    to_date: str | None = None,
    report_type: str = "summary",
    filters: str | dict | None = None,
):
    """Execute UQQC Item Summary or Device Details with multi-value filter support."""
    _require_report_access()
    kind = _normalize_report_type(report_type)
    start_date, end_date = _parse_date_range(from_date, to_date)
    parsed_filters = _parse_filters(filters, FILTER_FIELDS_BY_TYPE[kind])

    if kind == "summary":
        rows = _run_summary(start_date, end_date, parsed_filters)
        return {"columns": SUMMARY_COLUMNS, "result": rows}

    rows = _run_device(start_date, end_date, parsed_filters)
    return {"columns": DEVICE_COLUMNS, "result": rows}


def _require_report_access():
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    if user == "Administrator":
        return
    roles = set(frappe.get_roles(user))
    if roles.intersection(REPORT_ROLES):
        return
    if frappe.has_permission("UQQC Inspection Event", "report"):
        return
    frappe.throw(_("Not permitted"), frappe.PermissionError)


def _normalize_report_type(report_type):
    kind = str(report_type or "summary").strip().lower()
    if kind not in FILTER_FIELDS_BY_TYPE:
        frappe.throw(_("Invalid UQQC report type."), frappe.ValidationError)
    return kind


def _parse_date_range(raw_from, raw_to):
    if not raw_from or not raw_to:
        frappe.throw(_("Choose both report dates."), frappe.ValidationError)
    try:
        start = frappe.utils.getdate(str(raw_from).strip())
        end = frappe.utils.getdate(str(raw_to).strip())
    except (TypeError, ValueError):
        frappe.throw(_("Choose valid report dates."), frappe.ValidationError)
    if start > end:
        frappe.throw(_("The start date must be on or before the end date."), frappe.ValidationError)
    return start.isoformat(), end.isoformat()


def _parse_filters(raw_filters, allowed_fields):
    if isinstance(raw_filters, str):
        try:
            raw_filters = json.loads(raw_filters) if raw_filters.strip() else {}
        except json.JSONDecodeError:
            raw_filters = {}
    if not isinstance(raw_filters, dict):
        return {}

    parsed = {}
    for field in allowed_fields:
        values = _normalize_values(raw_filters.get(field))
        if values:
            parsed[field] = tuple(values)
    return parsed


def _normalize_values(raw):
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                decoded = json.loads(text)
                if isinstance(decoded, list):
                    raw = decoded
                else:
                    raw = [text]
            except json.JSONDecodeError:
                raw = [text]
        else:
            raw = [text]
    elif not isinstance(raw, (list, tuple, set)):
        raw = [raw]

    return list(dict.fromkeys(
        str(item).strip()
        for item in raw
        if item is not None and str(item).strip()
    ))


def _query_filter_rows(kind):
    """Return distinct filter combinations for the report dropdowns.

    Wraps the 900k-row event table in a DISTINCT subquery first, so joins
    operate on ~165 unique tuples instead of the full table — cutting query
    time from ~16 s to ~4 s without any schema changes.
    """
    if kind == "device":
        subquery_fields = "device, line, product, market, color, size"
        select_fields = [
            f"{QC_EXPR} AS qc",
            "company.name AS companyId",
            "company.company_code AS companyCode",
            "company.company_name AS companyName",
            "product.name AS productId",
            "product.product_code AS productCode",
            "product.product_name AS productName",
            "device.name AS deviceId",
            "device.device_name AS deviceName",
            "market.name AS marketId",
            "market.code AS marketCode",
            "market.name_en AS marketName",
            "color.name AS colorId",
            "color.color_code AS colorCode",
            "color.color_name AS colorName",
            "size.name AS sizeId",
            "size.size_code AS sizeCode",
            "size.size_label AS sizeLabel",
        ]
        extra_joins = DEVICE_JOINS
        order_by = "companyName, deviceName, productCode, marketName, colorCode, sizeLabel, qc"
    else:
        subquery_fields = "device, line, product"
        select_fields = [
            f"{QC_EXPR} AS qc",
            "company.name AS companyId",
            "company.company_code AS companyCode",
            "company.company_name AS companyName",
            "product.name AS productId",
            "product.product_code AS productCode",
            "product.product_name AS productName",
        ]
        extra_joins = ""
        order_by = "companyName, companyCode, productCode, qc"

    subquery = f"SELECT DISTINCT {subquery_fields} FROM `tabUQQC Inspection Event`"
    from_clause = (
        f"FROM ({subquery}) e "
        "JOIN `tabFactory Device` device ON device.name = e.device "
        "JOIN `tabProduction Line` line ON line.name = e.line AND line.company = device.company "
        "JOIN `tabCompany` company ON company.name = line.company "
        "JOIN `tabProduct` product ON product.name = e.product"
    )
    sql = f"SELECT DISTINCT {', '.join(select_fields)} {from_clause}{extra_joins} ORDER BY {order_by}"
    return frappe.db.sql(sql, as_dict=True)


def _in_clause(expr, field, values, params):
    placeholders = []
    for index, value in enumerate(values):
        key = f"{field}_{index}"
        placeholders.append(f"%({key})s")
        params[key] = value
    return f"{expr} IN ({', '.join(placeholders)})"


def _where_clauses(parsed_filters, fields, qc_in_inner=True):
    clauses = []
    params = {}
    for field in fields:
        values = parsed_filters.get(field)
        if not values:
            continue
        if field == "qc":
            if qc_in_inner:
                clauses.append(_in_clause(QC_EXPR, "qc", values, params))
            continue
        clauses.append(_in_clause(FILTER_COLUMN_MAP[field], field, values, params))
    return (" AND " + " AND ".join(clauses) if clauses else ""), params


def _run_summary(start_date, end_date, parsed_filters):
    daily_extra, params = _where_clauses(parsed_filters, ("company", "product"), qc_in_inner=False)
    params.update({"from_date": start_date, "to_date": end_date})

    outer_where = ""
    if parsed_filters.get("qc"):
        outer_where = " WHERE " + _in_clause("daily.deviceQc", "qc", parsed_filters["qc"], params)

    sql = f"""
        SELECT
            daily.occurredOn AS occurredOn,
            daily.deviceQc AS deviceQc,
            daily.companyName AS companyName,
            daily.sampleCode AS sampleCode,
            daily.pass AS pass,
            daily.rework AS rework,
            daily.defect AS defect,
            daily.pass + daily.defect AS inspected,
            CASE
                WHEN daily.pass + daily.defect = 0 THEN 0
                ELSE ROUND(100.0 * daily.defect / (daily.pass + daily.defect), 2)
            END AS defectRate,
            COALESCE(totals.totalRework, 0) AS totalRework,
            COALESCE(totals.totalPass, 0) AS totalPass,
            COALESCE(totals.totalDefect, 0) AS totalDefect,
            COALESCE(totals.totalPass, 0) + COALESCE(totals.totalDefect, 0) AS totalInspected,
            CASE
                WHEN COALESCE(totals.totalPass, 0) + COALESCE(totals.totalDefect, 0) = 0 THEN 0
                ELSE ROUND(100.0 * COALESCE(totals.totalDefect, 0) / (COALESCE(totals.totalPass, 0) + COALESCE(totals.totalDefect, 0)), 2)
            END AS totalDefectRate
        FROM (
            SELECT
                DATE(DATE_ADD(e.occurred_at, INTERVAL 7 HOUR)) AS occurredOn,
                {QC_EXPR} AS deviceQc,
                company.company_code AS companyCode,
                company.company_name AS companyName,
                product.product_code AS sampleCode,
                SUM(CASE WHEN e.event_kind = 'pass' THEN e.quantity ELSE 0 END) AS pass,
                SUM(CASE WHEN e.event_kind = 'rework' THEN e.quantity ELSE 0 END) AS rework,
                SUM(CASE WHEN e.event_kind = 'defect' THEN e.quantity ELSE 0 END) AS defect
            {BASE_FROM}
            WHERE {DATE_RANGE_WHERE}{daily_extra}
            GROUP BY DATE(DATE_ADD(e.occurred_at, INTERVAL 7 HOUR)), deviceQc, company.company_code, company.company_name, product.product_code
        ) daily
        LEFT JOIN (
            SELECT
                {QC_EXPR} AS deviceQc,
                company.company_code AS companyCode,
                product.product_code AS sampleCode,
                SUM(CASE WHEN e.event_kind = 'pass' THEN e.quantity ELSE 0 END) AS totalPass,
                SUM(CASE WHEN e.event_kind = 'rework' THEN e.quantity ELSE 0 END) AS totalRework,
                SUM(CASE WHEN e.event_kind = 'defect' THEN e.quantity ELSE 0 END) AS totalDefect
            {BASE_FROM}
            GROUP BY deviceQc, company.company_code, product.product_code
        ) totals ON totals.deviceQc = daily.deviceQc AND totals.companyCode = daily.companyCode AND totals.sampleCode = daily.sampleCode
        {outer_where}
        ORDER BY daily.occurredOn, daily.deviceQc, daily.companyCode, daily.sampleCode
    """
    rows = frappe.db.sql(sql, params, as_dict=True)
    return _format_rows(rows, SUMMARY_COLUMNS)


def _run_device(start_date, end_date, parsed_filters):
    extra_where, params = _where_clauses(
        parsed_filters,
        ("qc", "company", "product", "device", "market", "color", "size"),
        qc_in_inner=True,
    )
    params.update({"from_date": start_date, "to_date": end_date})

    sql = f"""
        SELECT
            company.company_name AS companyName,
            DATE(DATE_ADD(e.occurred_at, INTERVAL 7 HOUR)) AS occurredOn,
            {QC_EXPR} AS deviceQc,
            device.device_name AS deviceName,
            product.product_code AS sampleCode,
            market.name_en AS marketName,
            color.color_code AS colorCode,
            size.size_label AS sizeLabel,
            SUM(CASE WHEN e.event_kind = 'pass' THEN e.quantity ELSE 0 END) AS pass,
            SUM(CASE WHEN e.event_kind = 'rework' THEN e.quantity ELSE 0 END) AS rework,
            SUM(CASE WHEN e.event_kind = 'defect' THEN e.quantity ELSE 0 END) AS defect
        {BASE_FROM}{DEVICE_JOINS}
        WHERE {DATE_RANGE_WHERE}{extra_where}
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
        ORDER BY company.company_name, occurredOn, device.device_name, product.product_code, market.name_en, color.color_code, size.size_label
    """
    rows = frappe.db.sql(sql, params, as_dict=True)
    return _format_rows(rows, DEVICE_COLUMNS)


def _format_rows(rows, columns):
    int_fields = {col["fieldname"] for col in columns if col["fieldtype"] == "Int"}
    float_fields = {col["fieldname"] for col in columns if col["fieldtype"] in ("Float", "Percent")}
    date_fields = {col["fieldname"] for col in columns if col["fieldtype"] == "Date"}

    formatted = []
    for row in rows:
        item = dict(row)
        for key in int_fields:
            item[key] = int(item.get(key) or 0)
        for key in float_fields:
            item[key] = float(item.get(key) or 0)
        for key in date_fields:
            val = item.get(key)
            if hasattr(val, "isoformat"):
                item[key] = val.isoformat()[:10]
            elif val is not None:
                item[key] = str(val)[:10]
        formatted.append(item)
    return formatted
