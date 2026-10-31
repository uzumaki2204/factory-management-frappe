"""Import historical UQQC events using catalog codes in Frappe Data Import."""

from collections import Counter, defaultdict, deque
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from html import escape
import json
from zoneinfo import ZoneInfo

import frappe
from frappe.core.doctype.data_import.import_provider import ImportProvider
from frappe.core.doctype.data_import.importer import ACTION_INSERT, ACTION_UPDATE, INSERT

from factory_management.uqqc.api import EVENT_IDENTITY_FIELDS, _event_identity, _event_uid
from factory_management.uqqc.i18n import text


EVENT_TYPE = "UQQC Inspection Event"
LOCAL_ZONE = ZoneInfo("Asia/Ho_Chi_Minh")
LINKS = {
    "device": ("Factory Device", ("device_name",), ("company",)),
    "line": ("Production Line", ("line_code",), ("company",)),
    "product": ("Product", ("product_code",), ()),
    "color": ("Product Color", ("color_code",), ()),
    "size": ("ProductSize", ("size_code", "size_label"), ()),
    "market": ("Market", ("code",), ()),
    "defect": ("UQQC Defect", ("code",), ("record_type",)),
    "defect_position": ("UQQC Defect Position", ("code",), ("record_type",)),
}
REQUIRED_LINKS = frozenset(("device", "line", "product", "color", "size", "market"))
SOURCE_FIELDS = (
    "local_event_id", "device", "event_kind", "line", "product", "color", "size", "market",
    "defect", "defect_position", "defect_piece_id", "schema_version", "quantity", "occurred_at", "synced_at",
)
CANONICAL_FIELDS = tuple(field for field in EVENT_IDENTITY_FIELDS if field != "local_event_id")


def _token(value):
    return "" if value is None else str(value).strip()


def _chunks(values, size=500):
    values = list(values)
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def _raw_signature(doc):
    return tuple(_token(doc.get(field)) for field in SOURCE_FIELDS)


def _db_datetime(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _timestamp(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        parsed = datetime.fromisoformat(_token(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_ZONE)
    return parsed.astimezone(timezone.utc)


def _positive_int(value):
    try:
        number = Decimal(_token(value))
        if number.is_finite() and number > 0 and number == int(number):
            return int(number)
    except (InvalidOperation, ValueError, OverflowError):
        pass
    raise ValueError


def _issue(issues, key, row, **values):
    issues.append((key, row, values))


def _format_rows(rows):
    ordered = sorted(set(rows))
    ranges = []
    start = previous = ordered[0]
    for row in ordered[1:]:
        if row == previous + 1:
            previous = row
            continue
        ranges.append(str(start) if start == previous else f"{start}–{previous}")
        start = previous = row
    ranges.append(str(start) if start == previous else f"{start}–{previous}")
    return ", ".join(ranges)


def _warnings(issues):
    grouped = defaultdict(list)
    for key, row, values in issues:
        grouped[(key, tuple(sorted(values.items())))].append(row)
    result = []
    for (key, values), rows in grouped.items():
        arguments = {name: escape(str(value)) for name, value in values}
        count_key = "import.row_count_one" if len(rows) == 1 else "import.row_count_many"
        arguments.update(
            rows=_format_rows(rows),
            count=len(rows),
            row_count=text(count_key).format(count=len(rows)),
        )
        result.append({"row": rows[0], "message": text("import." + key).format(**arguments)})
    return result


def _lookup_maps(payloads):
    tokens = {field: set() for field in LINKS}
    for payload in payloads:
        for field in LINKS:
            value = _token(payload.doc.get(field))
            if value:
                tokens[field].add(value)
    maps = {}
    for field, (doctype, aliases, extras) in LINKS.items():
        selected = tokens[field]
        records = {}
        columns = list(dict.fromkeys(("name", *aliases, *extras)))
        for selector in ("name", *aliases):
            for batch in _chunks(selected):
                for record in frappe.get_all(
                    doctype, fields=columns, filters={selector: ["in", batch]}, limit_page_length=0,
                ):
                    records[record.name] = dict(record)
        matched = defaultdict(dict)
        for record in records.values():
            for selector in ("name", *aliases):
                value = _token(record.get(selector))
                if value:
                    matched[value.casefold()][record["name"]] = record
        maps[field] = matched
    return maps


def _prepare(raw, maps, row, now, issues):
    if _token(raw.get("name")):
        _issue(issues, "id_must_be_blank", row)
    event = {}
    related = {}
    invalid_required_link = False
    for field in LINKS:
        value = _token(raw.get(field))
        if not value:
            if field in REQUIRED_LINKS:
                _issue(issues, "required", row, field=text("field." + field))
                invalid_required_link = True
            event[field] = None
            continue
        candidates = maps[field].get(value.casefold(), {})
        if not candidates:
            _issue(issues, "missing_link", row, field=text("field." + field), value=value)
            event[field] = None
            if field in REQUIRED_LINKS:
                invalid_required_link = True
            continue
        if len(candidates) != 1:
            _issue(issues, "ambiguous_link", row, field=text("field." + field), value=value)
            event[field] = None
            if field in REQUIRED_LINKS:
                invalid_required_link = True
            continue
        related[field] = next(iter(candidates.values()))
        event[field] = related[field]["name"]
    if "device" in related and "line" in related and related["device"]["company"] != related["line"]["company"]:
        _issue(issues, "line_company", row)
    for field, expected in (("defect", "Defect"), ("defect_position", "Position")):
        if field in related and related[field]["record_type"] != expected:
            _issue(issues, "wrong_catalog_type", row, field=text("field." + field))
    kind = _token(raw.get("event_kind")).lower()
    if kind not in ("defect", "pass", "rework"):
        _issue(issues, "event_kind", row)
    if kind == "defect" and not _token(raw.get("defect")):
        _issue(issues, "defect_required", row)
    if kind in ("pass", "rework") and (event.get("defect") or event.get("defect_position")):
        _issue(issues, "quantity_detail", row)
    event["event_kind"] = kind
    event["defect_piece_id"] = _token(raw.get("defect_piece_id")) or None
    try:
        event["quantity"] = _positive_int(raw.get("quantity"))
    except ValueError:
        _issue(issues, "quantity", row)
    version = _token(raw.get("schema_version"))
    try:
        event["schema_version"] = _positive_int(version) if version else (1 if kind == "defect" else None)
    except ValueError:
        _issue(issues, "schema_version", row)
    try:
        occurred = _timestamp(raw.get("occurred_at"))
        event["occurred_at"] = _db_datetime(occurred)
    except (TypeError, ValueError, OverflowError):
        _issue(issues, "occurred_at", row)
        occurred = None
    synced_value = _token(raw.get("synced_at"))
    try:
        synced = _timestamp(raw.get("synced_at")) if synced_value else now
        event["synced_at"] = _db_datetime(synced)
        if synced > now + timedelta(minutes=5):
            _issue(issues, "future_synced_at", row)
        if occurred and synced < occurred:
            _issue(issues, "synced_before_occurred", row)
    except (TypeError, ValueError, OverflowError):
        _issue(issues, "synced_at", row)
    local_id = _token(raw.get("local_event_id"))
    if len(local_id) > 100:
        _issue(issues, "local_event_id_length", row)
    event["local_event_id"] = local_id
    return event if not invalid_required_link and all(field in event for field in CANONICAL_FIELDS) else None


def _canonical(event):
    return json.dumps([event.get(field) for field in CANONICAL_FIELDS], ensure_ascii=False, separators=(",", ":"))


def _generated_id(canonical, ordinal):
    digest = sha256(json.dumps([canonical, ordinal], ensure_ascii=False).encode("utf-8")).hexdigest()
    return "uqqc-import-" + digest


def _analyze(import_file):
    payloads = import_file.get_payloads_for_import()
    maps = _lookup_maps(payloads)
    issues = []
    prepared = []
    occurrences = Counter()
    identities = {}
    now = datetime.now(timezone.utc)
    for payload in payloads:
        row = payload.rows[0].row_number
        event = _prepare(payload.doc, maps, row, now, issues)
        if event is None:
            continue
        canonical = _canonical(event)
        if not event["local_event_id"]:
            occurrences[canonical] += 1
            event["local_event_id"] = _generated_id(canonical, occurrences[canonical])
        uid = _event_uid(event)
        identity = _event_identity(event)
        if uid in identities:
            _issue(issues, "duplicate_local_event_id", row)
        identities[uid] = identity
        prepared.append((row, _raw_signature(payload.doc), event, uid))
    for batch in _chunks(identities):
        for stored in frappe.get_all(
            EVENT_TYPE, fields=["name", *EVENT_IDENTITY_FIELDS],
            filters={"name": ["in", batch]}, limit_page_length=0,
        ):
            if _event_identity(stored) != identities[stored.name]:
                for row, _signature, _event, uid in prepared:
                    if uid == stored.name:
                        _issue(issues, "existing_conflict", row)
    return prepared, _warnings(issues)


class UqqcInspectionEventImportProvider(ImportProvider):
    """Resolve catalog codes while retaining Frappe's Data Import permissions and logs."""

    def get_import_fields(self):
        fields = []
        for df in frappe.get_meta(EVENT_TYPE).fields:
            entry = df.as_dict()
            entry["parent"] = EVENT_TYPE
            if entry["fieldname"] in LINKS:
                entry["fieldtype"] = "Data"
                entry["options"] = None
            if entry["fieldname"] in ("local_event_id", "synced_at"):
                entry["reqd"] = 0
                entry["read_only"] = 0
            fields.append(entry)
        return {"fields": fields}

    def validate(self, import_file):
        if import_file.import_type != INSERT:
            return [{"message": text("import.insert_only")}]
        _prepared, warnings = _analyze(import_file)
        return warnings

    def _runtime(self, importer):
        if hasattr(self, "_pending"):
            return
        prepared, warnings = _analyze(importer.import_file)
        if warnings:
            frappe.throw(warnings[0]["message"], frappe.ValidationError)
        successful = set()
        if importer.data_import.name:
            for log in frappe.get_all(
                "Data Import Log", fields=["row_indexes"],
                filters={"data_import": importer.data_import.name, "success": 1}, limit_page_length=0,
            ):
                successful.update(json.loads(log.row_indexes or "[]"))
        skipped = {int(row.row_number) for row in (importer.data_import.get("skipped_rows") or [])}
        pending = defaultdict(deque)
        for row, signature, event, uid in prepared:
            if row not in successful and row not in skipped:
                pending[signature].append((row, event, uid))
        self._pending = pending

    def import_row(self, importer, doc):
        if importer.import_type != INSERT:
            frappe.throw(text("import.insert_only"), frappe.ValidationError)
        self._runtime(importer)
        signature = _raw_signature(doc)
        if not self._pending[signature]:
            frappe.throw(text("import.row_unavailable"), frappe.ValidationError)
        row, event, uid = self._pending[signature][0]
        stored = frappe.db.get_value(EVENT_TYPE, uid, EVENT_IDENTITY_FIELDS, as_dict=True, for_update=True)
        if stored:
            if _event_identity(stored) != _event_identity(event):
                frappe.throw(text("import.existing_conflict").format(rows=row, count=1), frappe.ValidationError)
            self._pending[signature].popleft()
            return frappe.get_doc(EVENT_TYPE, uid), ACTION_UPDATE
        created = frappe.get_doc({"doctype": EVENT_TYPE, **event})
        created.insert(set_name=uid, ignore_if_duplicate=True)
        stored = frappe.db.get_value(EVENT_TYPE, uid, EVENT_IDENTITY_FIELDS, as_dict=True, for_update=True)
        if not stored or _event_identity(stored) != _event_identity(event):
            frappe.throw(text("import.existing_conflict").format(rows=row, count=1), frappe.ValidationError)
        self._pending[signature].popleft()
        return created, ACTION_INSERT
