"""SQL projections matching the navigation and soft-delete rules in .NET."""

import json


class ReportRepository:
    def __init__(self, reader):
        self.reader = reader

    def events(self, query, quantity=False, mode="summary"):
        table = "QCBrotherInspectionQuantityEvents" if quantity else "QCBrotherInspectionEvents"
        fields = {
            "deviceNo": "v.DeviceName", "companyCode": "c.Code", "companyName": "c.Name",
            "sampleCode": "p.Code",
        }
        joins = [_join("ProductionLines", "l", "e.LineId"),
                 _join("Devices", "v", "e.DeviceActivationId"),
                 _join("Companies", "c", "e.CompanyId"), _join("Products", "p", "e.ProductId")]
        if mode != "totals":
            fields.update(occurredAt="e.OccurredAt", countryCode="m.Code", countryName="m.Name",
                          colorCode="co.Code", sizeCode="s.Code", sizeName="s.Name")
            joins += [_join("Markets", "m", "e.MarketId"), _join("Colors", "co", "e.ColorId"),
                      _join("Sizes", "s", "e.SizeId")]
        if mode == "summary":
            fields.update(factoryCode="f.Code", lineCode="l.Code", lineName="l.Name")
            joins.append(_join("Factories", "f", "l.FactoryId"))
            if not quantity:
                fields.update(defectCode="d.Code", defectName="d.Name",
                              positionCode="dp.Code", positionName="dp.Name")
                joins += [_join("QCDefects", "d", "e.DefectId"),
                          _join("QCDefectPositions", "dp", "e.DefectPositionId", optional=True)]
        event = "CASE e.EventType WHEN 1 THEN 'PASS' ELSE 'REWORK' END" if quantity else "''"
        fields["eventNo"] = event
        value = "e.Quantity" if quantity else "e.QuantityDelta"
        where, parameters = _event_filters(query)
        if quantity:
            where.append("e.EventType IN (1, 2)")
            if query.event_no in ("PASS", "REWORK"):
                where.append("e.EventType = ?")
                parameters.append(1 if query.event_no == "PASS" else 2)
        sql = "SELECT " + ", ".join(f"{value} AS [{key}]" for key, value in fields.items())
        sql += f", {'SUM(' + value + ')' if mode == 'totals' else value} AS quantity"
        sql += f" FROM dbo.[{table}] e " + " ".join(joins) + " WHERE " + " AND ".join(where)
        if mode == "totals":
            groups = [value for key, value in fields.items() if key != "eventNo"]
            if quantity:
                groups.append("e.EventType")
            sql += " GROUP BY " + ", ".join(groups)
        return self.reader.rows(sql, parameters)

    def legacy(self, query, mode="summary"):
        where, parameters = ["e.IsDeleted = 0"], []
        start, finish = query.bounds(legacy=True)
        if start is not None:
            where += ["e.OccurredOn >= ?", "e.OccurredOn < ?"]
            parameters += [start, finish]
        if query.qc:
            where.append("CHARINDEX(?, UPPER(e.SerialNo)) > 0")
            parameters.append(query.qc)
        if query.sample_code:
            where.append("(e.ItemId = ? OR LEFT(e.ItemId, LEN(?) + 1) = ?)")
            parameters += [query.sample_code, query.sample_code, query.sample_code + "."]
        if query.event_no == "PASS":
            where.append("e.EvntNo = '0041'")
        fields = {"serialNo": "e.SerialNo", "itemId": "e.ItemId", "eventNo": "e.EvntNo"}
        if mode == "summary":
            fields.update(occurredAt="e.OccurredOn", paramsJson="e.ParamsJson")
        elif mode == "daily":
            fields["occurredAt"] = "CAST(e.OccurredOn AS date)"
        sql = "SELECT " + ", ".join(f"{value} AS [{key}]" for key, value in fields.items())
        sql += ", " + ("1" if mode == "summary" else "COUNT(*)") + " AS quantity"
        sql += " FROM dbo.QCBrother e WHERE " + " AND ".join(where)
        if mode != "summary":
            sql += " GROUP BY " + ", ".join(fields.values())
        return self.reader.rows(sql, parameters)

    def lines(self):
        return self.reader.rows("""SELECT l.CompanyId AS companyId, l.Code AS lineCode,
            l.Name AS lineName, c.Code AS companyCode, c.Name AS companyName, f.Code AS factoryCode
            FROM dbo.ProductionLines l
            LEFT JOIN dbo.Companies c ON c.Id = l.CompanyId AND c.IsDeleted = 0
            LEFT JOIN dbo.Factories f ON f.Id = l.FactoryId AND f.IsDeleted = 0
            WHERE l.IsDeleted = 0""")

    def order_details(self, keys):
        dimensions = [sorted({key[index] for key in keys}) for index in range(4)]
        return self.reader.rows("""SELECT d.PurchaseOrderId AS purchaseOrderId,
            d.SampleCode AS sampleCode, m.Code AS countryCode, co.Code AS colorCode,
            s.Code AS sizeCode, po.PONumber AS poNumber, d.OrderQty AS orderQty
            FROM dbo.PurchaseOrderDetails d
            INNER JOIN dbo.PurchaseOrders po ON po.Id = d.PurchaseOrderId AND po.IsDeleted = 0
            INNER JOIN dbo.Markets m ON m.Id = po.MarketId AND m.IsDeleted = 0
            INNER JOIN dbo.Colors co ON co.Id = d.ColorId AND co.IsDeleted = 0
            INNER JOIN dbo.Sizes s ON s.Id = d.SizeId AND s.IsDeleted = 0
            WHERE d.IsDeleted = 0
            AND d.SampleCode IN (SELECT value FROM OPENJSON(?))
            AND m.Code IN (SELECT value FROM OPENJSON(?))
            AND co.Code IN (SELECT value FROM OPENJSON(?))
            AND s.Code IN (SELECT value FROM OPENJSON(?))""",
                                [json.dumps(values, ensure_ascii=False) for values in dimensions])

    def order_revisions(self, numbers):
        return self.reader.rows("""SELECT Id AS id, PONumber AS poNumber, RevisionNo AS revisionNo,
            Status AS status, DocumentStatusExternal AS documentStatus
            FROM dbo.PurchaseOrders WHERE IsDeleted = 0
            AND PONumber IN (SELECT value FROM OPENJSON(?))""",
                                [json.dumps(sorted(numbers), ensure_ascii=False)])


def _join(table, alias, reference, optional=False):
    kind = "LEFT" if optional else "INNER"
    return f"{kind} JOIN dbo.[{table}] {alias} ON {alias}.Id = {reference} AND {alias}.IsDeleted = 0"


def _event_filters(query):
    where, parameters = ["e.IsDeleted = 0", "l.CompanyId = e.CompanyId"], []
    start, finish = query.bounds()
    if start is not None:
        where += ["e.OccurredAt >= ?", "e.OccurredAt < ?"]
        parameters += [start, finish]
    for value, expression in ((query.company_id, "e.CompanyId = ?"),
                              (query.company_code, "c.Code = ?"),
                              (query.qc, "CHARINDEX(?, UPPER(v.DeviceName)) > 0"),
                              (query.sample_code, "p.Code = ?")):
        if value:
            where.append(expression)
            parameters.append(value)
    return where, parameters
