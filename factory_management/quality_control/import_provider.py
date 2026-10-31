"""Import historical QC events using catalog codes in Frappe Data Import."""

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

from factory_management.i18n import message


EVENT_TYPE = "QC Inspection Event"
LOCAL_ZONE = ZoneInfo("Asia/Ho_Chi_Minh")
LINKS = {
    "device": ("Factory Device", ("device_name",), ("company", "line")),
    "product": ("Product", ("product_code",), ()),
    "line": ("Production Line", ("line_code",), ("company",)),
    "color": ("Product Color", ("color_code",), ()),
    "size": ("ProductSize", ("size_code", "size_label"), ()),
    "defect": ("QC Defect", ("code",), ("record_type",)),
}
LINK_FIELDS = tuple(LINKS)
REQUIRED_FIELDS = frozenset(("device", "event_type", "occurred_at"))
SOURCE_FIELDS = (
    "name", "device", "local_event_id", "event_type", "product", "line", "color", "size",
    "defect", "quantity_delta", "occurred_at", "synced_at",
)
EVENT_IDENTITY_FIELDS = (
    "device", "local_event_id", "event_type", "product", "line", "color", "size",
    "defect", "quantity_delta", "occurred_at",
)
CANONICAL_FIELDS = tuple(field for field in EVENT_IDENTITY_FIELDS if field != "local_event_id")
FIELD_LABELS = {
    "device": "IMPORT_QC_FIELD_DEVICE",
    "event_type": "IMPORT_QC_FIELD_EVENT_TYPE",
    "occurred_at": "IMPORT_QC_FIELD_OCCURRED_AT",
    "product": "IMPORT_QC_FIELD_PRODUCT",
    "line": "IMPORT_QC_FIELD_LINE",
    "color": "IMPORT_QC_FIELD_COLOR",
    "size": "IMPORT_QC_FIELD_SIZE",
    "defect": "IMPORT_QC_FIELD_DEFECT",
}


def _text(key):
    language = (getattr(frappe.local, "lang", None) or "vi").split("-")[0]
    return message(key, lang=language)


def _token(value):
    return "" if value is None else str(value).strip()


def _chunks(values, size=500):
    values = list(values)
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def _raw_signature(doc):
    return tuple(_token(doc.get(field)) for field in SOURCE_FIELDS)


def _payload_doc(payload):
    """Return a mapped import document, or None while columns are unmapped."""
    document = getattr(payload, "doc", None)
    return document if callable(getattr(document, "get", None)) else None


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


def _server_zone():
    name = frappe.db.get_single_value("System Settings", "time_zone") or "Asia/Ho_Chi_Minh"
    try:
        return ZoneInfo(name)
    except (KeyError, ValueError):
        return LOCAL_ZONE


def _quantity_delta(value):
    if _token(value) == "":
        return 0
    try:
        number = Decimal(_token(value))
        if number.is_finite() and number == int(number):
            return int(number)
    except (InvalidOperation, ValueError, OverflowError):
        pass
    raise ValueError


def _issue(issues, key, row, **values):
    issues.append((key, row, values))


def _format_rows(rows):
    ordered = sorted(set(rows))
    if not ordered:
        return ""
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
    grouped = defaultdict(set)
    for key, row, values in issues:
        grouped[(key, tuple(sorted(values.items())))].add(row)

    warnings = []
    for (key, values), rows in sorted(grouped.items()):
        rows = sorted(rows)
        arguments = {name: escape(str(value)) for name, value in values}
        count_key = "IMPORT_QC_ROW_COUNT_ONE" if len(rows) == 1 else "IMPORT_QC_ROW_COUNT_MANY"
        arguments.update(rows=_format_rows(rows), count=len(rows), row_count=_text(count_key).format(count=len(rows)))
        rendered = _text(key).format(**arguments)
        warnings.extend({"row": row, "message": rendered} for row in rows)
    return warnings


def _lookup_field(field, tokens):
    doctype, aliases, extras = LINKS[field]
    columns = list(dict.fromkeys(("name", *aliases, *extras)))
    records = {}
    for selector in ("name", *aliases):
        for batch in _chunks(tokens):
            for record in frappe.get_all(
                doctype,
                fields=columns,
                filters={selector: ["in", batch]},
                limit_page_length=0,
            ):
                records[record.name] = dict(record)

    by_value = defaultdict(dict)
    by_name = defaultdict(dict)
    for record in records.values():
        name = _token(record.get("name"))
        if name:
            by_name[name.casefold()][name] = record
        for selector in ("name", *aliases):
            value = _token(record.get(selector))
            if value:
                by_value[value.casefold()][name] = record
    return {"values": by_value, "names": by_name, "records": records}


def _lookup_maps(payloads):
    tokens = {field: set() for field in LINKS}
    for payload in payloads:
        document = _payload_doc(payload)
        if document is None:
            continue
        for field in LINKS:
            value = _token(document.get(field))
            if value:
                tokens[field].add(value)

    maps = {"device": _lookup_field("device", tokens["device"])}
    # A blank Line inherits the Device's assigned line, matching QC sync_events.
    tokens["line"].update(
        _token(record.get("line"))
        for record in maps["device"]["records"].values()
        if _token(record.get("line"))
    )
    maps["line"] = _lookup_field("line", tokens["line"])
    for field in ("product", "color", "size", "defect"):
        maps[field] = _lookup_field(field, tokens[field])
    return maps


def _resolve_link(raw, field, maps, row, issues):
    value = _token(raw.get(field))
    if not value:
        if field in REQUIRED_FIELDS:
            _issue(issues, "IMPORT_QC_REQUIRED", row, field=_text(FIELD_LABELS[field]))
            return None, None, True
        return None, None, False

    matches = maps[field]["values"].get(value.casefold(), {})
    if not matches:
        _issue(
            issues,
            "IMPORT_QC_MISSING_LINK",
            row,
            field=_text(FIELD_LABELS[field]),
            value=value,
        )
        return None, None, field in REQUIRED_FIELDS
    if len(matches) != 1:
        _issue(
            issues,
            "IMPORT_QC_AMBIGUOUS_LINK",
            row,
            field=_text(FIELD_LABELS[field]),
            value=value,
        )
        return None, None, field in REQUIRED_FIELDS
    record = next(iter(matches.values()))
    return record["name"], record, False


def _prepare(raw, maps, row, now, server_zone, issues):
    if _token(raw.get("name")):
        _issue(issues, "IMPORT_QC_ID_MUST_BE_BLANK", row)

    event = {}
    related = {}
    invalid_required = False
    for field in LINK_FIELDS:
        resolved, record, invalid = _resolve_link(raw, field, maps, row, issues)
        event[field] = resolved
        if record:
            related[field] = record
        invalid_required = invalid_required or invalid

    raw_line = _token(raw.get("line"))
    if not raw_line and related.get("device"):
        default_line = _token(related["device"].get("line"))
        if default_line:
            line_matches = maps["line"]["names"].get(default_line.casefold(), {})
            if len(line_matches) == 1:
                related["line"] = next(iter(line_matches.values()))
                event["line"] = related["line"]["name"]
            elif not line_matches:
                _issue(
                    issues,
                    "IMPORT_QC_MISSING_LINK",
                    row,
                    field=_text(FIELD_LABELS["line"]),
                    value=default_line,
                )
            else:
                _issue(
                    issues,
                    "IMPORT_QC_AMBIGUOUS_LINK",
                    row,
                    field=_text(FIELD_LABELS["line"]),
                    value=default_line,
                )

    device = related.get("device")
    line = related.get("line")
    if device and line and (not device.get("company") or line.get("company") != device.get("company")):
        _issue(issues, "IMPORT_QC_LINE_COMPANY", row)

    defect = related.get("defect")
    if defect and defect.get("record_type") != "Defect":
        _issue(issues, "IMPORT_QC_WRONG_DEFECT_TYPE", row)

    event_type = _token(raw.get("event_type"))
    if not event_type:
        _issue(issues, "IMPORT_QC_REQUIRED", row, field=_text(FIELD_LABELS["event_type"]))
        invalid_required = True
    elif len(event_type) > 100:
        _issue(issues, "IMPORT_QC_EVENT_TYPE_LENGTH", row)
    event["event_type"] = event_type

    try:
        event["quantity_delta"] = _quantity_delta(raw.get("quantity_delta"))
    except ValueError:
        _issue(issues, "IMPORT_QC_QUANTITY", row)

    occurred_value = raw.get("occurred_at")
    if not _token(occurred_value):
        _issue(issues, "IMPORT_QC_REQUIRED", row, field=_text(FIELD_LABELS["occurred_at"]))
        invalid_required = True
        occurred = None
    else:
        try:
            occurred = _timestamp(occurred_value)
            event["occurred_at"] = _db_datetime(occurred)
            event["server_date_key"] = occurred.astimezone(server_zone).date().isoformat()
        except (TypeError, ValueError, OverflowError):
            _issue(issues, "IMPORT_QC_OCCURRED_AT_INVALID", row)
            invalid_required = True
            occurred = None

    synced_value = _token(raw.get("synced_at"))
    try:
        synced = _timestamp(raw.get("synced_at")) if synced_value else now
        event["synced_at"] = _db_datetime(synced)
        if synced > now + timedelta(minutes=5):
            _issue(issues, "IMPORT_QC_FUTURE_SYNCED_AT", row)
        if occurred and synced < occurred:
            _issue(issues, "IMPORT_QC_SYNCED_BEFORE_OCCURRED", row)
    except (TypeError, ValueError, OverflowError):
        _issue(issues, "IMPORT_QC_SYNCED_AT_INVALID", row)
        event["synced_at"] = None

    local_id = _token(raw.get("local_event_id"))
    if len(local_id) > 100:
        _issue(issues, "IMPORT_QC_LOCAL_EVENT_ID_LENGTH", row)
    event["local_event_id"] = local_id
    return None if invalid_required else event


def _canonical(event):
    return json.dumps(
        [event.get(field) for field in CANONICAL_FIELDS],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _generated_id(canonical, ordinal):
    digest = sha256(json.dumps([canonical, ordinal], ensure_ascii=False).encode("utf-8")).hexdigest()
    return "qc-import-" + digest


def _event_uid(event):
    return sha256((event["device"] + "|" + event["local_event_id"].casefold()).encode("utf-8")).hexdigest()


def _event_identity(event):
    values = []
    for field in EVENT_IDENTITY_FIELDS:
        value = event.get(field)
        if field == "occurred_at":
            value = datetime.fromisoformat(str(value)).strftime("%Y-%m-%d %H:%M:%S.%f")
        elif field == "quantity_delta":
            value = int(value or 0)
        else:
            value = str(value or "")
        values.append(value)
    return tuple(values)


def _analyze(import_file):
    payloads = [
        (payload, document)
        for payload in import_file.get_payloads_for_import()
        if (document := _payload_doc(payload)) is not None
    ]
    if not payloads:
        # Frappe calls provider validation before column mapping in the preview
        # step. At that point each payload has doc=None and core warnings guide
        # the user to map the columns.
        return [], [], {}

    mapped_payloads = [payload for payload, _document in payloads]
    maps = _lookup_maps(mapped_payloads)
    issues = []
    prepared = []
    occurrences = Counter()
    identities = defaultdict(list)
    now = datetime.now(timezone.utc)
    server_zone = _server_zone()

    for payload, document in payloads:
        row = payload.rows[0].row_number
        event = _prepare(document, maps, row, now, server_zone, issues)
        if event is None:
            continue
        if not event["local_event_id"]:
            canonical = _canonical(event)
            occurrences[canonical] += 1
            event["local_event_id"] = _generated_id(canonical, occurrences[canonical])
        uid = _event_uid(event)
        identity = _event_identity(event)
        if identities[uid]:
            _issue(issues, "IMPORT_QC_DUPLICATE_LOCAL_EVENT_ID", row)
        identities[uid].append((row, identity))
        event["event_uid"] = uid
        prepared.append((row, _raw_signature(document), event, uid))

    existing = {}
    uids = list(identities)
    for batch in _chunks(uids):
        for stored in frappe.get_all(
            EVENT_TYPE,
            fields=["name", "event_uid", *EVENT_IDENTITY_FIELDS],
            filters={"event_uid": ["in", batch]},
            limit_page_length=0,
        ):
            stored = dict(stored)
            uid = stored["event_uid"]
            stored_identity = _event_identity(stored)
            for row, identity in identities[uid]:
                if identity != stored_identity:
                    _issue(issues, "IMPORT_QC_EXISTING_CONFLICT", row)
                else:
                    existing[uid] = stored

    return prepared, _warnings(issues), existing


def _cached_analysis(import_file):
    """Share one full-file analysis between preflight and row import."""
    cache_key = "_qc_import_analysis"
    if cache_key not in import_file.__dict__:
        import_file.__dict__[cache_key] = _analyze(import_file)
    return import_file.__dict__[cache_key]


class QCInspectionEventImportProvider(ImportProvider):
    """Resolve QC catalog codes and preserve normal Frappe import checks and logs."""

    def get_import_fields(self):
        fields = []
        generated_fields = {"event_uid", "server_date_key"}
        for field in frappe.get_meta(EVENT_TYPE).fields:
            entry = field.as_dict()
            fieldname = entry["fieldname"]
            if fieldname in generated_fields:
                continue
            entry["parent"] = EVENT_TYPE
            if fieldname in LINKS:
                entry["fieldtype"] = "Data"
                entry["options"] = None
            if fieldname in ("local_event_id", "synced_at"):
                entry["reqd"] = 0
                entry["read_only"] = 0
            fields.append(entry)
        return {"fields": fields}

    def validate(self, import_file):
        if import_file.import_type != INSERT:
            return [{"message": _text("IMPORT_QC_INSERT_ONLY")}]
        _prepared, warnings, _existing = _cached_analysis(import_file)
        return warnings

    def _runtime(self, importer):
        if getattr(self, "_runtime_checked", False):
            if failure := getattr(self, "_runtime_failure", None):
                raise failure
            if error := getattr(self, "_runtime_error", None):
                frappe.throw(error, frappe.ValidationError)
            return

        self._runtime_checked = True
        try:
            prepared, warnings, existing = _cached_analysis(importer.import_file)
            skipped = {
                int(row.row_number)
                for row in (importer.data_import.get("skipped_rows") or [])
            }
            blocking = [
                warning for warning in warnings
                if warning.get("row") is None or int(warning["row"]) not in skipped
            ]
            if blocking:
                self._runtime_error = blocking[0]["message"]
            else:
                successful = set()
                if importer.data_import.name:
                    logs = frappe.get_all(
                        "Data Import Log",
                        fields=["row_indexes"],
                        filters={"data_import": importer.data_import.name, "success": 1},
                        limit_page_length=0,
                    )
                    for log in logs:
                        successful.update(json.loads(log.row_indexes or "[]"))
                pending = defaultdict(deque)
                for row, signature, event, uid in prepared:
                    if row not in successful and row not in skipped:
                        pending[signature].append((row, event, uid))
                self._pending = pending
                self._existing = existing
        except Exception as error:
            self._runtime_failure = error
            raise

        if error := getattr(self, "_runtime_error", None):
            frappe.throw(error, frappe.ValidationError)

    def import_row(self, importer, doc):
        if importer.import_type != INSERT:
            frappe.throw(_text("IMPORT_QC_INSERT_ONLY"), frappe.ValidationError)
        self._runtime(importer)

        signature = _raw_signature(doc)
        if not self._pending[signature]:
            frappe.throw(_text("IMPORT_QC_ROW_UNAVAILABLE"), frappe.ValidationError)
        _row, event, uid = self._pending[signature][0]
        identity = _event_identity(event)
        if stored := self._existing.get(uid):
            if _event_identity(stored) != identity:
                frappe.throw(_text("IMPORT_QC_EXISTING_CONFLICT"), frappe.ValidationError)
            self._pending[signature].popleft()
            return frappe.get_doc(EVENT_TYPE, stored["name"]), ACTION_UPDATE

        created = frappe.get_doc({"doctype": EVENT_TYPE, **event})
        created.insert(ignore_if_duplicate=True)
        stored = frappe.db.get_value(
            EVENT_TYPE,
            {"event_uid": uid},
            ["name", *EVENT_IDENTITY_FIELDS],
            as_dict=True,
            for_update=True,
        )
        if not stored or _event_identity(stored) != identity:
            frappe.throw(_text("IMPORT_QC_EXISTING_CONFLICT"), frappe.ValidationError)
        self._existing[uid] = dict(stored)
        self._pending[signature].popleft()
        return created, ACTION_INSERT
