"""Code-based UQQC Data Import checks without a live Frappe database."""

import importlib.util
import json
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "factory_management/uqqc/import_provider.py"
CATALOG = json.loads((ROOT / "factory_management/public/uqqc/i18n.json").read_text(encoding="utf-8"))["en"]
FIELDS = (
    "device", "local_event_id", "event_kind", "line", "product", "color", "size", "market",
    "defect", "defect_position", "defect_piece_id", "schema_version", "quantity", "occurred_at",
)
META_FIELDS = (*FIELDS, "synced_at")


class Row(dict):
    __getattr__ = dict.get


class Database:
    def __init__(self):
        self.records = {}
        self.logs = []

    def get_value(self, doctype, name, fields, as_dict=False, for_update=False):
        assert doctype == "UQQC Inspection Event"
        record = self.records.get(name)
        return Row({field: record.get(field) for field in fields}) if record else None


def _identity(event):
    values = []
    for field in FIELDS:
        value = event.get(field)
        if field == "occurred_at":
            value = datetime.fromisoformat(str(value)).strftime("%Y-%m-%d %H:%M:%S.%f")
        elif field in ("quantity", "schema_version"):
            value = int(value or 0)
        else:
            value = str(value or "")
        values.append(value)
    return tuple(values)


def load_provider():
    masters = {
        "Factory Device": [Row(name="device-1", device_name="001QC1KT2", company="company-1")],
        "Production Line": [Row(name="323", line_code="323", company="company-1")],
        "Product": [Row(name="product-1", product_code="317H035A")],
        "Product Color": [Row(name="38", color_code="38")],
        "ProductSize": [Row(name="L", size_code="005", size_label="L")],
        "Market": [Row(name="04", code="04")],
        "UQQC Defect": [Row(name="UQQC-B10", code="B10", record_type="Defect")],
        "UQQC Defect Position": [Row(name="position-1", code="PLC0023", record_type="Position")],
    }
    database = Database()
    frappe = types.ModuleType("frappe")
    frappe.ValidationError = type("ValidationError", (Exception,), {})
    frappe.db = database

    def get_all(doctype, fields, filters, limit_page_length):
        if doctype == "UQQC Inspection Event":
            return [Row(name=name, **{field: record.get(field) for field in fields if field != "name"})
                    for name, record in database.records.items() if name in filters["name"][1]]
        if doctype == "Data Import Log":
            return database.logs
        selector, (_operator, tokens) = next(iter(filters.items()))
        return [record for record in masters[doctype]
                if str(record.get(selector, "")).casefold() in {str(token).casefold() for token in tokens}]

    frappe.get_all = get_all
    frappe.get_meta = lambda _doctype: types.SimpleNamespace(fields=[
        types.SimpleNamespace(as_dict=lambda field=field: {"fieldname": field, "fieldtype": "Link" if field == "device" else "Data", "reqd": 1, "read_only": 0})
        for field in META_FIELDS
    ])
    frappe.throw = lambda message, _error=None: (_ for _ in ()).throw(frappe.ValidationError(message))

    def get_doc(*args):
        if len(args) == 2:
            return Row(name=args[1], **database.records[args[1]])
        value = Row(args[0])

        def insert(set_name, ignore_if_duplicate):
            value.name = set_name
            database.records.setdefault(set_name, dict(value))

        value.insert = insert
        return value

    frappe.get_doc = get_doc
    api = types.ModuleType("factory_management.uqqc.api")
    api.EVENT_IDENTITY_FIELDS = FIELDS
    api._event_uid = lambda event: sha256((event["device"] + "|" + event["local_event_id"].casefold()).encode()).hexdigest()
    api._event_identity = _identity
    i18n = types.ModuleType("factory_management.uqqc.i18n")
    i18n.text = lambda key: CATALOG[key]
    provider_module = types.ModuleType("frappe.core.doctype.data_import.import_provider")
    provider_module.ImportProvider = type("ImportProvider", (), {})
    importer_module = types.ModuleType("frappe.core.doctype.data_import.importer")
    importer_module.ACTION_INSERT = "Insert"
    importer_module.ACTION_UPDATE = "Update"
    importer_module.INSERT = "Insert New Records"
    name = "factory_management.uqqc._import_provider_under_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch("zoneinfo.ZoneInfo", return_value=timezone(timedelta(hours=7))), patch.dict(sys.modules, {
        "frappe": frappe,
        "frappe.core": types.ModuleType("frappe.core"),
        "frappe.core.doctype": types.ModuleType("frappe.core.doctype"),
        "frappe.core.doctype.data_import": types.ModuleType("frappe.core.doctype.data_import"),
        "frappe.core.doctype.data_import.import_provider": provider_module,
        "frappe.core.doctype.data_import.importer": importer_module,
        "factory_management.uqqc.api": api,
        "factory_management.uqqc.i18n": i18n,
        name: module,
    }):
        spec.loader.exec_module(module)
    return module, frappe, database, masters


def source(**changes):
    record = Row(local_event_id="", device="001QC1KT2", event_kind="defect", line="323",
                 product="317H035A", color="38", size="L", market="04", defect="B10",
                 defect_position="PLC0023", defect_piece_id="", schema_version="",
                 quantity=2, occurred_at=datetime(2026, 10, 1), synced_at=datetime(2026, 10, 31))
    record.update(changes)
    return record


def import_file(*records):
    payloads = [Row(doc=record, rows=[Row(row_number=index)]) for index, record in enumerate(records, 2)]
    return types.SimpleNamespace(import_type="Insert New Records", get_payloads_for_import=lambda: payloads)


class UqqcImportProviderTests(unittest.TestCase):
    def test_codes_ids_dates_and_duplicate_rows(self):
        module, _frappe, _db, _masters = load_provider()
        file = import_file(source(), source())
        prepared, warnings = module._analyze(file)
        self.assertEqual(warnings, [])
        self.assertEqual(len(prepared), 2)
        self.assertNotEqual(prepared[0][2]["local_event_id"], prepared[1][2]["local_event_id"])
        self.assertEqual(prepared[0][2]["device"], "device-1")
        self.assertEqual(prepared[0][2]["product"], "product-1")
        self.assertEqual(prepared[0][2]["defect"], "UQQC-B10")
        self.assertEqual(prepared[0][2]["defect_position"], "position-1")
        self.assertEqual(prepared[0][2]["quantity"], 2)
        self.assertEqual(prepared[0][2]["occurred_at"], "2026-09-30 17:00:00.000000")
        self.assertEqual([row[3] for row in prepared], [row[3] for row in module._analyze(file)[0]])
        converted, warnings = module._analyze(import_file(source(device="device-1", product="product-1", size="005")))
        self.assertEqual(warnings, [])
        self.assertEqual(converted[0][3], prepared[0][3])

    def test_missing_ambiguous_future_and_company_mismatch_block_preview(self):
        module, _frappe, _db, masters = load_provider()
        masters["Product"].append(Row(name="product-2", product_code="317H035A"))
        masters["Production Line"][0]["company"] = "company-2"
        file = import_file(source(product="UNKNOWN", synced_at=datetime(2065, 1, 1)), source(),
                           source(product="product-1", synced_at=datetime(2065, 1, 1)))
        warnings = module.UqqcInspectionEventImportProvider().validate(file)
        messages = "\n".join(item["message"] for item in warnings)
        self.assertIn("UNKNOWN", messages)
        self.assertIn("future", messages)
        future = next(item for item in warnings if "future" in item["message"])
        self.assertIsNone(future["row"])
        self.assertIn("Rows: 2, 4 (2 rows).", future["message"])
        self.assertIn("multiple", messages)
        self.assertIn("different companies", messages)
        missing_defect = module.UqqcInspectionEventImportProvider().validate(
            import_file(source(defect="UNKNOWN_DEFECT"))
        )
        missing_defect_messages = "\n".join(item["message"] for item in missing_defect)
        self.assertIn("UNKNOWN_DEFECT", missing_defect_messages)
        self.assertNotIn("requires Defect", missing_defect_messages)

    def test_reference_warnings_are_skippable_and_bulk_date_warning_stays_compact(self):
        module, _frappe, _db, _masters = load_provider()
        self.assertEqual(module._format_rows([3, 4, 5, 7, 9, 10]), "3–5, 7, 9–10")
        warnings = module._warnings([
            ("missing_link", 3, {"field": "Product", "value": "UNKNOWN"}),
            ("missing_link", 4, {"field": "Product", "value": "UNKNOWN"}),
            ("future_synced_at", 3, {}),
            ("future_synced_at", 4, {}),
        ])
        row_warnings = [warning for warning in warnings if warning["row"] is not None]
        self.assertEqual([warning["row"] for warning in row_warnings], [3, 4])
        self.assertEqual(row_warnings[0]["message"], row_warnings[1]["message"])
        self.assertIn("Rows: 3–4 (2 rows).", row_warnings[0]["message"])
        global_warnings = [warning for warning in warnings if warning["row"] is None]
        self.assertEqual(len(global_warnings), 1)
        self.assertIn("Rows: 3–4 (2 rows).", global_warnings[0]["message"])

    def test_full_file_analysis_is_cached_for_preflight_and_import(self):
        module, _frappe, database, _masters = load_provider()
        file = import_file(source(), source())
        importer = types.SimpleNamespace(import_type="Insert New Records", import_file=file,
                                         data_import=Row(name=None, skipped_rows=[]))
        provider = module.UqqcInspectionEventImportProvider()
        with patch.object(module, "_analyze", wraps=module._analyze) as analyze:
            self.assertEqual(provider.validate(file), [])
            for payload in file.get_payloads_for_import():
                provider.import_row(importer, payload.doc)
        self.assertEqual(analyze.call_count, 1)
        self.assertEqual(len(database.records), 2)

    def test_skipping_invalid_rows_allows_valid_rows_to_import(self):
        module, _frappe, database, _masters = load_provider()
        file = import_file(source(product="UNKNOWN"), source(), source(defect="UNKNOWN_DEFECT"))
        provider = module.UqqcInspectionEventImportProvider()
        importer = types.SimpleNamespace(import_type="Insert New Records", import_file=file,
                                         data_import=Row(name="import-1", skipped_rows=[
                                             Row(row_number=2), Row(row_number=4)
                                         ]))
        with patch.object(module, "_analyze", wraps=module._analyze) as analyze:
            warnings = provider.validate(file)
            self.assertEqual({warning["row"] for warning in warnings}, {2, 4})
            payload = file.get_payloads_for_import()[1]
            _created, action = provider.import_row(importer, payload.doc)
        self.assertEqual(analyze.call_count, 1)
        self.assertEqual(action, "Insert")
        self.assertEqual(len(database.records), 1)

    def test_unskipped_invalid_row_still_blocks_without_reanalysis(self):
        module, frappe, _database, _masters = load_provider()
        file = import_file(source(product="UNKNOWN"), source())
        importer = types.SimpleNamespace(import_type="Insert New Records", import_file=file,
                                         data_import=Row(name="import-1", skipped_rows=[]))
        provider = module.UqqcInspectionEventImportProvider()
        with patch.object(module, "_analyze", wraps=module._analyze) as analyze:
            warnings = provider.validate(file)
            self.assertEqual([warning["row"] for warning in warnings], [2])
            for _ in range(2):
                with self.assertRaises(frappe.ValidationError):
                    provider.import_row(importer, file.get_payloads_for_import()[0].doc)
        self.assertEqual(analyze.call_count, 1)

    def test_insert_and_reimport_are_idempotent(self):
        module, _frappe, database, _masters = load_provider()
        file = import_file(source(), source())
        importer = types.SimpleNamespace(import_type="Insert New Records", import_file=file,
                                         data_import=Row(name=None, skipped_rows=[]))
        provider = module.UqqcInspectionEventImportProvider()
        for payload in file.get_payloads_for_import():
            provider.import_row(importer, payload.doc)
        self.assertEqual(len(database.records), 2)
        provider = module.UqqcInspectionEventImportProvider()
        for payload in file.get_payloads_for_import():
            provider.import_row(importer, payload.doc)
        self.assertEqual(len(database.records), 2)

    def test_retry_skips_logged_duplicate_row_and_keeps_next_ordinal(self):
        module, _frappe, database, _masters = load_provider()
        file = import_file(source(), source())
        first, second = module._analyze(file)[0]
        database.records[first[3]] = first[2]
        database.logs.append(Row(row_indexes="[2]"))
        importer = types.SimpleNamespace(import_type="Insert New Records", import_file=file,
                                         data_import=Row(name="import-1", skipped_rows=[]))
        provider = module.UqqcInspectionEventImportProvider()
        created, action = provider.import_row(importer, file.get_payloads_for_import()[1].doc)
        self.assertEqual(action, "Insert")
        self.assertEqual(created.name, second[3])
        self.assertEqual(set(database.records), {first[3], second[3]})

    def test_blank_synced_at_uses_server_clock(self):
        module, _frappe, _database, _masters = load_provider()
        prepared, warnings = module._analyze(import_file(source(synced_at=None)))
        self.assertEqual(warnings, [])
        synced = datetime.fromisoformat(prepared[0][2]["synced_at"]).replace(tzinfo=timezone.utc)
        self.assertLess(abs(datetime.now(timezone.utc) - synced), timedelta(minutes=1))

    def test_import_schema_accepts_codes_and_auto_filled_fields(self):
        module, _frappe, _db, _masters = load_provider()
        fields = {field["fieldname"]: field for field in module.UqqcInspectionEventImportProvider().get_import_fields()["fields"]}
        self.assertEqual(fields["device"]["fieldtype"], "Data")
        self.assertEqual(fields["local_event_id"]["reqd"], 0)
        self.assertEqual(fields["synced_at"]["reqd"], 0)


if __name__ == "__main__":
    unittest.main()
