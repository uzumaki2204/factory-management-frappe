"""DTO projections and grouping compatible with QCBrotherInspectionReportService."""

from collections import defaultdict
from datetime import datetime, time

from .model import LegacyResolver, clean, device_qc, local_day, po_key
from .orders import purchase_order_values


DIMENSIONS = ("companyCode", "companyName", "sampleCode", "countryCode", "countryName",
              "colorCode", "sizeCode", "sizeName")
DETAILS = ("factoryCode", "lineCode", "lineName", "defectCode", "defectName", "positionCode", "positionName")
SUMMARY_SORT = ("occurredOn", "eventNo", "companyCode", "deviceQc", "deviceNo", "sampleCode",
                "countryCode", "colorCode", "sizeCode", "lineCode", "defectCode", "positionCode")
AGGREGATE_SORT = ("occurredOn", "companyCode", "serialNo", "deviceQc", "sampleCode",
                  "countryCode", "colorCode", "sizeCode")


class ReportService:
    def __init__(self, repository):
        self.repository = repository
        self._resolver = None

    def summary(self, query):
        grouped = defaultdict(int)
        columns = ("occurredOn", "eventNo", "deviceNo", "deviceQc") + DIMENSIONS + DETAILS
        for row in self._sources(query, "summary"):
            item = {field: clean(row.get(field)) for field in columns}
            item.update(occurredOn=datetime.combine(local_day(row, query.zone), time.min, query.zone).isoformat(),
                        deviceQc=device_qc(row.get("deviceNo")))
            grouped[tuple(item[field] for field in columns)] += int(row["quantity"])
        items = [dict(zip(columns, key), quantity=quantity) for key, quantity in grouped.items()]
        orders = purchase_order_values(self.repository, items)
        for item in items:
            item["poNumbers"] = orders.get(po_key(item), "")
        return _ordered(items, SUMMARY_SORT)

    def aggregate(self, query):
        columns = ("occurredOn", "serialNo", "deviceQc") + DIMENSIONS
        daily = defaultdict(_counts)
        for row in self._sources(query, "daily"):
            local = datetime.combine(local_day(row, query.zone), time.min, query.zone)
            item = {field: clean(row.get(field)) for field in DIMENSIONS}
            item.update(occurredOn=local.isoformat(), serialNo=clean(row.get("deviceNo")),
                        deviceQc=device_qc(row.get("deviceNo")))
            _add(daily[tuple(item[field] for field in columns)], row)
        if not daily:
            return []
        totals = defaultdict(_counts)
        for row in self._sources(query.all_time(), "totals"):
            _add(totals[_total_key(row)], row)
        items = []
        for key, counts in daily.items():
            item = dict(zip(columns, key), **counts)
            overall = totals[_total_key(item)]
            item.update({"total" + name.title(): count for name, count in overall.items()})
            items.append(item)
        plans = purchase_order_values(self.repository, items, planned=True)
        for item in items:
            item["plannedQuantity"] = plans.get(po_key(item), 0)
        return _ordered(items, AGGREGATE_SORT)

    def _sources(self, query, mode):
        if not query.event_no:
            yield from self.repository.events(query, mode=mode)
        if query.event_no in ("", "PASS", "REWORK"):
            yield from self.repository.events(query, quantity=True, mode=mode)
        if query.event_no not in ("", "PASS"):
            return
        if self._resolver is None:
            self._resolver = LegacyResolver(self.repository.lines())
        for raw in self.repository.legacy(query, mode):
            row = self._resolver.resolve(raw, query, summary=mode == "summary")
            if row is not None:
                yield row


def _counts():
    return {"pass": 0, "rework": 0, "defect": 0}


def _add(counts, row):
    event = clean(row.get("eventNo")).upper()
    counts[event.lower() if event in ("PASS", "REWORK") else "defect"] += int(row["quantity"])


def _total_key(row):
    return (row.get("deviceQc", device_qc(row.get("deviceNo"))),
            *(clean(row.get(key)) for key in ("companyCode", "companyName", "sampleCode")))


def _ordered(items, fields):
    return sorted(items, key=lambda item: tuple(item[field] for field in fields))
