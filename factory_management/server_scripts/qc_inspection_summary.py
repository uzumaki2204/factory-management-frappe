# Editable in Frappe Desk: Server Script / QC Inspection Summary.
# API Method: qc-inspection-summary. All dates use the UTC date of occurred_at.
frappe.call("factory_management.api_access.authorize_inspection_summary")

start_text = frappe.form_dict.get("date_from")
end_text = frappe.form_dict.get("date_to")
if not start_text or not end_text:
    frappe.throw(_("QC_REPORT_DATES_REQUIRED"), frappe.ValidationError)
try:
    start = frappe.utils.getdate(start_text)
    end = frappe.utils.getdate(end_text)
except (ValueError, TypeError):
    frappe.throw(_("QC_REPORT_INVALID_DATE"), frappe.ValidationError)
if start > end:
    start, end = end, start
if (end - start).days > 6:
    frappe.throw(_("QC_REPORT_RANGE_TOO_LONG"), frappe.ValidationError)

params = {"date_from": str(start), "date_to": str(end)}
conditions = []
filters = {
    "event_type": ("e.event_type", "contains"),
    "entity_type": ("e.entity_type", "contains"),
    "device_name": ("d.device_name", "contains"),
    "device_no": ("LEFT(d.device_name, 3)", "prefix"),
    "device_qc": ("SUBSTRING(d.device_name, 4, 3)", "prefix"),
    "device_company": ("SUBSTRING(d.device_name, 7)", "contains"),
    "companies_code": ("c.company_code", "prefix"),
    "companies_name": ("c.company_name", "contains"),
    "factories_code": ("f.factory_code", "prefix"),
    "factories_name": ("f.factory_name", "contains"),
    "production_lines_code": ("pl.line_code", "prefix"),
    "production_lines_name": ("pl.line_name", "contains"),
    "customers_code": ("cu.customer_code", "prefix"),
    "customers_name": ("cu.customer_name", "contains"),
    "products_code": ("p.product_code", "prefix"),
    "products_name": ("p.product_name", "contains"),
    "colors_code": ("cl.color_code", "prefix"),
    "colors_name": ("cl.color_name", "contains"),
    "sizes_code": ("s.size_code", "prefix"),
    "sizes_name": ("s.size_label", "contains"),
    "qc_defect_groups_code": ("qdg.code", "prefix"),
    "qc_defect_groups_name": ("qdg.title", "contains"),
    "qc_defects_code": ("qd.code", "prefix"),
    "qc_defects_name": ("qd.title", "contains"),
}
for name, rule in filters.items():
    raw = frappe.form_dict.get(name)
    if raw is not None and str(raw).strip():
        value = str(raw).strip()[:500]
        if rule[1] == "contains":
            params[name] = "%" + value + "%"
        else:
            params[name] = value + "%"
        conditions.append(rule[0] + " LIKE %(" + name + ")s")

quantity = frappe.form_dict.get("quantity_summary")
having = ""
if quantity is not None and str(quantity).strip():
    try:
        params["quantity_summary"] = int(quantity)
    except (ValueError, TypeError):
        frappe.throw(_("QC_REPORT_INVALID_QUANTITY"), frappe.ValidationError)
    having = " HAVING SUM(COALESCE(e.quantity_delta, 0)) = %(quantity_summary)s"

where_extra = ""
if conditions:
    where_extra = " AND " + " AND ".join(conditions)

query = """
SELECT
    e.event_type AS eventType,
    e.entity_type AS entityType,
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
    CAST(SUM(COALESCE(e.quantity_delta, 0)) AS SIGNED) AS quantitySummary
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
LEFT JOIN `tabQC Defect Group` qdg ON qdg.name = qd.defect_group
LEFT JOIN `tabSize` s ON s.name = e.size
LEFT JOIN `tabProduct Color` cl ON cl.name = e.color
WHERE e.occurred_at >= %(date_from)s
  AND e.occurred_at < DATE_ADD(%(date_to)s, INTERVAL 1 DAY)
""" + where_extra + """
GROUP BY e.event_type, e.entity_type, DATE(e.occurred_at), d.device_name,
         c.company_code, c.company_name, f.factory_code, f.factory_name,
         pl.line_code, pl.line_name, lg.group_code, lg.group_name,
         cu.customer_code, cu.customer_name, p.product_code, p.product_name,
         cl.color_code, cl.color_name, s.size_code, s.size_label,
         qdg.code, qdg.title, qd.code, qd.title
""" + having + """
ORDER BY occurredDate, deviceName, productsCode, productionLinesCode,
         qcDefectsCode
"""
frappe.response["message"] = frappe.db.sql(query, params, as_dict=True)
