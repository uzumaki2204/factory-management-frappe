"""Read Frappe UQQC events and SPL purchase orders for QCBrother reports."""

import frappe

from .model import ReportSourceError
from .service import ReportService


class UqqcReportService(ReportService):
    """Use the .NET-compatible report projections without legacy rows."""

    def _sources(self, query, mode):
        if not query.event_no:
            yield from self.repository.events(query, mode=mode)
        if query.event_no in ("", "PASS", "REWORK"):
            yield from self.repository.events(query, quantity=True, mode=mode)


class UqqcRepository:
    def __init__(self, company_id_code=None):
        self.company_id_code = company_id_code

    def events(self, query, quantity=False, mode="summary"):
        if query.company_id and not self.company_id_code:
            return []
        start, finish = query.bounds()
        conditions = [
            "line.company = device.company",
            "e.event_kind IN ('pass', 'rework')" if quantity else "e.event_kind = 'defect'",
        ]
        values = []
        if start is not None:
            conditions[:0] = ["e.occurred_at >= %s", "e.occurred_at < %s"]
            values.extend((start, finish))
        if not quantity:
            conditions.append("defect.name IS NOT NULL")
        if query.company_id:
            conditions.append("company.company_code = %s")
            values.append(self.company_id_code)
        if query.company_code:
            conditions.append("company.company_code = %s")
            values.append(query.company_code)
        if query.qc:
            conditions.append("LOCATE(%s, UPPER(device.device_name)) > 0")
            values.append(query.qc)
        if query.sample_code:
            conditions.append("product.product_code = %s")
            values.append(query.sample_code)
        if quantity and query.event_no:
            conditions.append("e.event_kind = %s")
            values.append(query.event_no.lower())

        selection = """e.occurred_at AS `occurredAt`,
                   CASE e.event_kind WHEN 'pass' THEN 'PASS'
                       WHEN 'rework' THEN 'REWORK' ELSE '' END AS `eventNo`,
                   device.device_name AS `deviceNo`,
                   company.company_code AS `companyCode`,
                   company.company_name AS `companyName`,
                   factory.factory_code AS `factoryCode`,
                   product.product_code AS `sampleCode`,
                   market.code AS `countryCode`, market.name_en AS `countryName`,
                   color.color_code AS `colorCode`,
                   size.size_code AS `sizeCode`, size.size_label AS `sizeName`,
                   line.line_code AS `lineCode`, line.line_name AS `lineName`,
                   defect.code AS `defectCode`, defect.title AS `defectName`,
                   defect_position.code AS `positionCode`,
                   defect_position.title AS `positionName`,
                   e.quantity AS `quantity`"""
        if mode == "totals":
            selection = """CASE e.event_kind WHEN 'pass' THEN 'PASS'
                        WHEN 'rework' THEN 'REWORK' ELSE '' END AS `eventNo`,
                   device.device_name AS `deviceNo`,
                   company.company_code AS `companyCode`,
                   company.company_name AS `companyName`,
                   product.product_code AS `sampleCode`,
                   SUM(e.quantity) AS `quantity`"""
        statement = "SELECT " + selection + """
              FROM `tabUQQC Inspection Event` e
              JOIN `tabFactory Device` device ON device.name = e.device
              JOIN `tabProduction Line` line ON line.name = e.line
              JOIN `tabCompany` company ON company.name = line.company
              LEFT JOIN `tabFactory` factory ON factory.name = line.factory
              JOIN `tabProduct` product ON product.name = e.product
              JOIN `tabMarket` market ON market.name = e.market
              JOIN `tabProduct Color` color ON color.name = e.color
              JOIN `tabProductSize` size ON size.name = e.size
              LEFT JOIN `tabUQQC Defect` defect ON defect.name = e.defect
              LEFT JOIN `tabUQQC Defect Position` defect_position
                ON defect_position.name = e.defect_position
             WHERE """ + " AND ".join(conditions)
        if mode == "totals":
            statement += """
             GROUP BY e.event_kind, device.device_name, company.company_code,
                      company.company_name, product.product_code"""
        return _rows(statement, values)

    def order_details(self, keys):
        if not keys:
            return []
        dimensions = [sorted({key[index] for key in keys}) for index in range(4)]
        clauses = [", ".join(["%s"] * len(values)) for values in dimensions]
        statement = """
            SELECT item.parent AS `purchaseOrderId`, item.sample_code AS `sampleCode`,
                   market.code AS `countryCode`, color.color_code AS `colorCode`,
                   size.size_code AS `sizeCode`, po.po_number AS `poNumber`,
                   item.order_qty AS `orderQty`
              FROM `tabSPL Purchase Order Item` item
              JOIN `tabSPL Purchase Order` po ON po.name = item.parent
              JOIN `tabMarket` market ON market.name = po.market
              JOIN `tabProduct Color` color ON color.name = item.product_color
              JOIN `tabProductSize` size ON size.name = item.size
             WHERE item.parenttype = 'SPL Purchase Order'
               AND item.parentfield = 'items'
               AND item.sample_code IN ({})
               AND market.code IN ({})
               AND color.color_code IN ({})
               AND size.size_code IN ({})
        """.format(*clauses)
        return _rows(statement, [value for group in dimensions for value in group])

    def order_revisions(self, numbers):
        if not numbers:
            return []
        values = sorted(numbers)
        placeholders = ", ".join(["%s"] * len(values))
        statement = """
            SELECT po.name AS `id`, po.po_number AS `poNumber`,
                   po.revision_no AS `revisionNo`, po.status AS `status`,
                   po.document_status_external AS `documentStatus`
              FROM `tabSPL Purchase Order` po
             WHERE po.po_number IN ({})
        """.format(placeholders)
        return _rows(statement, values)


def _rows(statement, values):
    try:
        return frappe.db.sql(statement, values, as_dict=True)
    except Exception:
        raise ReportSourceError("QCBROTHER_UQQC_UNAVAILABLE") from None
