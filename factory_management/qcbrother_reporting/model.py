"""Contract normalization shared by the SQL reader and report projections."""

import json
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from uuid import UUID


class ReportInputError(ValueError):
    pass


class ReportSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReportQuery:
    begin: date | None
    end: date | None
    zone: tzinfo
    company_id: str = ""
    company_code: str = ""
    qc: str = ""
    sample_code: str = ""
    event_no: str = ""

    @classmethod
    def parse(cls, begin, end, zone, max_days, company_id=None, company_code=None,
              qc=None, sample_code=None, event_no=None):
        if not begin or not end:
            raise ReportInputError("QCBROTHER_RANGE_REQUIRED")
        try:
            first, last = sorted((_parse_date(begin), _parse_date(end)))
            last + timedelta(days=1)
        except (TypeError, ValueError, OverflowError):
            raise ReportInputError("QCBROTHER_RANGE_INVALID") from None
        if (last - first).days >= max_days:
            raise ReportInputError(f"QCBROTHER_RANGE_MAX_{max_days}")
        try:
            identity = UUID(clean(company_id)) if clean(company_id) else None
        except (ValueError, AttributeError):
            raise ReportInputError("QCBROTHER_COMPANY_ID_INVALID") from None
        return cls(first, last, zone, str(identity) if identity and identity.int else "",
                   clean(company_code), clean(qc).upper(), clean(sample_code), clean(event_no).upper())

    def all_time(self):
        return replace(self, begin=None, end=None, event_no="")

    def bounds(self, legacy=False):
        if self.begin is None:
            return None, None
        start = datetime.combine(self.begin, time.min)
        finish = datetime.combine(self.end + timedelta(days=1), time.min)
        if not legacy:
            start = start.replace(tzinfo=self.zone).astimezone(timezone.utc).replace(tzinfo=None)
            finish = finish.replace(tzinfo=self.zone).astimezone(timezone.utc).replace(tzinfo=None)
        return start, finish

    def matches_company(self, row):
        return (not self.company_id or str(row["companyId"]).lower() == self.company_id) and (
            not self.company_code or clean(row["companyCode"]).upper() == self.company_code.upper())


class LegacyResolver:
    def __init__(self, lines):
        self.by_code = defaultdict(list)
        for line in lines:
            self.by_code[clean(line["lineCode"]).upper()].append(line)

    def resolve(self, raw, query, summary=False):
        row = _legacy_fields(raw)
        candidates = self.by_code.get(row["lineCode"].upper(), [])
        company_candidates = [line for line in candidates if line.get("companyCode") is not None]
        company = _unique_company(company_candidates)
        if company is None and row["lineName"]:
            company = _unique_company(_named(company_candidates, row["lineName"]))
        if company is None or not query.matches_company(company):
            return None
        row.update({key: company[key] for key in ("companyCode", "companyName")})
        if summary:
            factories = [line for line in candidates if line["companyId"] == company["companyId"]]
            row["factoryCode"] = _unique_factory(factories)
            if not row["factoryCode"] and row["lineName"]:
                row["factoryCode"] = _unique_factory(_named(factories, row["lineName"]))
        return row


def clean(value):
    return "" if value is None else str(value).strip()


def device_qc(value):
    text = clean(value).upper()
    markers = [(text.find(code), code) for code in ("QC1", "QC2") if code in text]
    return min(markers)[1] if markers else ""


def local_day(row, zone):
    occurred = row["occurredAt"]
    if isinstance(occurred, date) and not isinstance(occurred, datetime):
        return occurred
    if row.get("legacy"):
        return occurred.date()
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)
    return occurred.astimezone(zone).date()


def po_key(row):
    return tuple(clean(row.get(key)) for key in ("sampleCode", "countryCode", "colorCode", "sizeCode"))


def _parse_date(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def _legacy_fields(raw):
    row = {"occurredAt": raw.get("occurredAt"), "legacy": True,
           "deviceNo": clean(raw["serialNo"]),
           "eventNo": "PASS" if clean(raw["eventNo"]).upper() == "0041" else "",
           "quantity": int(raw.get("quantity", 1))}
    for key in ("sampleCode", "countryCode", "countryName", "colorCode", "sizeCode", "sizeName",
                "lineCode", "lineName", "defectCode", "defectName", "positionCode", "positionName"):
        row[key] = ""
    parts = (raw.get("itemId") or "").split(".")
    if len(parts) >= 5:
        row["sampleCode"], row["colorCode"] = clean(parts[0]), clean(parts[2])
        for index, prefix in ((1, "country"), (3, "size"), (4, "line")):
            row[prefix + "Code"], row[prefix + "Name"] = _code_name(parts[index])
    elif len(parts) == 4:
        row.update(sampleCode=clean(parts[0]), countryCode=clean(parts[2]), colorCode=clean(parts[3]))
    if not row["eventNo"]:
        try:
            values = json.loads(raw.get("paramsJson") or "null")
        except (TypeError, ValueError):
            values = None
        if isinstance(values, list):
            for index, prefix in ((2, "defect"), (6, "position")):
                if len(values) > index and isinstance(values[index], str):
                    row[prefix + "Code"], row[prefix + "Name"] = _code_name(values[index])
    return row


def _code_name(value):
    code, separator, name = clean(value).partition("-")
    return code.strip(), name.strip() if separator else ""


def _unique_company(lines):
    companies = {str(line["companyId"]): line for line in lines}
    return next(iter(companies.values())) if len(companies) == 1 else None


def _named(lines, name):
    return [line for line in lines if clean(line["lineName"]).upper() == clean(name).upper()]


def _unique_factory(lines):
    codes = {}
    for line in lines:
        code = clean(line.get("factoryCode"))
        if code:
            codes.setdefault(code.upper(), code)
    return next(iter(codes.values())) if len(codes) == 1 else ""
