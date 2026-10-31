"""Code-based QC Data Import checks without a live Frappe database."""

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
MODULE_PATH = ROOT / "factory_management/quality_control/import_provider.py"
CATALOG = json.loads(
    (ROOT / "factory_management/public/js/qc-i18n.json").read_text(encoding="utf-8")
)
FIELDS = (
    "device", "local_event_id", "event_type", "product", "line", "color", "size",
    "defect", "quantity_delta", "occurred_at",
)
META_FIELDS = (*FIELDS, "event_uid", "synced_at", "server_date_key")


class Row(dict):
    __getattr__ = dict.get


class Database:
    def __init__(self):
        self.records = {}
        self.logs = []
        self.single_value_reads = 0

    def get_single_value(self, doctype, fieldname):
        assert (doctype, fieldname) == ("System Settings", "time_zone")
        self.single_value_reads += 1
        return "Asia/Ho_Chi_Minh"

    def get_all_events(self, event_uids):
        return [record for record in self.records.values() if record["event_uid"] in event_uids]

    def get_value(self, doctype, name_or_filters, fields, as_dict=False, for_update=False):
        assert doctype == "QC Inspection Event"
        if isinstance(name_or_filters, dict):
            event_uid = name_or_filters["event_uid"]
            record = next(
                (value for value in self.records.values() if value["event_uid"] == event_uid),
                None,
            )
        else:
            record = self.records.get(name_or_filters)
        if not record:
            return None
        return Row({field: record.get(field) for field in fields})


def load_provider():
    masters = {
        "Factory Device": [
            Row(name="device-1", device_name="001QC1KT2", company="company-1", line="line-1"),
            Row(name="device-2", device_name="002QC2KT2", company="company-2", line="line-2"),
        ],
        "Production Line": [
            Row(name="line-1", line_code="001", company="company-1"),
            Row(name="line-2", line_code="002", company="company-2"),
        ],
        "Product": [Row(name="product-1", product_code="0017H035A")],
        "Product Color": [Row(name="38", color_code="038")],
        "ProductSize": [Row(name="L", size_code="005", size_label="Large")],
        "QC Defect": [
            Row(name="defect-1", code="B10", record_type="Defect", is_active=0),
            Row(name="defect-group", code="G10", record_type="Group", is_active=1),
        ],
    }
    database = Database()
    frappe = types.ModuleType("frappe")
    frappe.ValidationError = type("ValidationError", (Exception,), {})
    frappe.local = Row(lang="vi")
    frappe.db = database
    frappe.calls = []

    def get_all(doctype, fields, filters, limit_page_length):
        frappe.calls.append((doctype, filters))
        if doctype == "QC Inspection Event":
            return database.get_all_events(set(filters["event_uid"][1]))
        if doctype == "Data Import Log":
            return database.logs
        selector, (_operator, tokens) = next(iter(filters.items()))
        wanted = {str(token).casefold() for token in tokens}
        return [
            record for record in masters[doctype]
            if str(record.get(selector) or "").casefold() in wanted
        ]

    frappe.get_all = get_all
    frappe.get_meta = lambda _doctype: types.SimpleNamespace(fields=[
        types.SimpleNamespace(as_dict=lambda field=field: {
            "fieldname": field,
            "fieldtype": "Link" if field in {"device", "product", "line", "color", "size", "defect"} else "Data",
            "reqd": 1,
            "read_only": 0,
        })
        for field in META_FIELDS
    ])
    frappe.throw = lambda message, _error=None: (
        (_ for _ in ()).throw(frappe.ValidationError(message))
    )

    def get_doc(*args):
        if len(args) == 2:
            return Row(database.records[args[1]])
        value = Row(args[0])

        def insert(ignore_if_duplicate=False):
            value.name = "event-" + value.event_uid[:12]
            if value.event_uid not in {row["event_uid"] for row in database.records.values()}:
                database.records[value.name] = {**value, "name": value.name}
            return value

        value.insert = insert
        return value

    frappe.get_doc = get_doc
    i18n = types.ModuleType("factory_management.i18n")
    i18n.message = lambda key, lang="vi": CATALOG.get(lang, CATALOG["vi"])[key]
    provider_module = types.ModuleType("frappe.core.doctype.data_import.import_provider")
    provider_module.ImportProvider = type("ImportProvider", (), {})
    importer_module = types.ModuleType("frappe.core.doctype.data_import.importer")
    importer_module.ACTION_INSERT = "Insert"
    importer_module.ACTION_UPDATE = "Update"
    importer_module.INSERT = "Insert New Records"
    name = "factory_management.quality_control._import_provider_under_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch("zoneinfo.ZoneInfo", return_value=timezone(timedelta(hours=7))), patch.dict(
        sys.modules,
        {
            "frappe": frappe,
            "frappe.core": types.ModuleType("frappe.core"),
            "frappe.core.doctype": types.ModuleType("frappe.core.doctype"),
            "frappe.core.doctype.data_import": types.ModuleType("frappe.core.doctype.data_import"),
            "frappe.core.doctype.data_import.import_provider": provider_module,
            "frappe.core.doctype.data_import.importer": importer_module,
            "factory_management.i18n": i18n,
            name: module,
        },
    ):
        spec.loader.exec_module(module)
    return module, frappe, database, masters


def source(**changes):
    record = Row(
        name="",
        device="001QC1KT2",
        local_event_id="",
        event_type="DefectAdd",
        product="0017H035A",
        line="",
        color="038",
        size="Large",
        defect="B10",
        quantity_delta=-2,
        occurred_at=datetime(2026, 10, 1, 2),
        synced_at=datetime(2026, 10, 1, 3),
    )
    record.update(changes)
    return record


def import_file(*records, import_type="Insert New Records"):
    payloads = [
        Row(doc=record, rows=[Row(row_number=index)])
        for index, record in enumerate(records, 2)
    ]
    return types.SimpleNamespace(
        import_type=import_type,
        get_payloads_for_import=lambda: payloads,
    )


class QCImportProviderTests(unittest.TestCase):
    def test_preview_without_column_mapping_skips_provider_analysis(self):
        module, frappe, database, _masters = load_provider()
        file = types.SimpleNamespace(
            import_type="Insert New Records",
            get_payloads_for_import=lambda: [
                Row(doc=None, rows=[Row(row_number=2)])
            ],
        )

        warnings = module.QCInspectionEventImportProvider().validate(file)

        self.assertEqual(warnings, [])
        self.assertEqual(frappe.calls, [])
        self.assertEqual(database.single_value_reads, 0)

    def test_codes_and_ids_resolve_and_timezone_is_converted_to_utc(self):
        module, _frappe, _database, _masters = load_provider()
        prepared, warnings, _existing = module._analyze(
            import_file(source(), source(device="device-1", product="product-1", size="005"))
        )
        self.assertEqual(warnings, [])
        self.assertEqual(len(prepared), 2)
        event = prepared[0][2]
        self.assertEqual(event["device"], "device-1")
        self.assertEqual(event["line"], "line-1")
        self.assertEqual(event["product"], "product-1")
        self.assertEqual(event["color"], "38")
        self.assertEqual(event["size"], "L")
        self.assertEqual(event["defect"], "defect-1")
        self.assertEqual(event["quantity_delta"], -2)
        self.assertEqual(event["occurred_at"], "2026-09-30 19:00:00.000000")
        self.assertEqual(event["server_date_key"], "2026-10-01")
        self.assertNotEqual(prepared[0][3], prepared[1][3])

    def test_explicit_timezone_and_local_event_id_are_preserved(self):
        module, _frappe, _database, _masters = load_provider()
        prepared, warnings, _existing = module._analyze(import_file(
            source(local_event_id="qc-source-42", occurred_at="2026-10-01T03:00:00+09:00",
                   synced_at="2026-10-01T04:00:00+09:00")
        ))
        self.assertEqual(warnings, [])
        event = prepared[0][2]
        self.assertEqual(event["local_event_id"], "qc-source-42")
        self.assertEqual(event["occurred_at"], "2026-09-30 18:00:00.000000")
        self.assertEqual(event["synced_at"], "2026-09-30 19:00:00.000000")
        self.assertEqual(
            event["event_uid"],
            sha256(b"device-1|qc-source-42").hexdigest(),
        )

    def test_missing_ambiguous_wrong_type_and_company_mismatch_are_reported(self):
        module, frappe, _database, masters = load_provider()
        frappe.local.lang = "en"
        masters["Product"].append(Row(name="product-2", product_code="0017H035A"))
        warnings = module.QCInspectionEventImportProvider().validate(import_file(
            source(product="MISSING"),
            source(product="0017H035A"),
            source(defect="G10"),
            source(device="002QC2KT2", line="001"),
        ))
        messages = "\n".join(item["message"] for item in warnings)
        self.assertIn("MISSING", messages)
        self.assertIn("multiple", messages)
        self.assertIn("Defect", messages)
        self.assertIn("different companies", messages)

    def test_grouped_warnings_can_skip_invalid_rows_and_import_valid_rows(self):
        module, frappe, database, _masters = load_provider()
        frappe.local.lang = "en"
        file = import_file(source(product="MISSING"), source(product="MISSING"), source())
        provider = module.QCInspectionEventImportProvider()
        importer = types.SimpleNamespace(
            import_type="Insert New Records",
            import_file=file,
            data_import=Row(name="import-1", skipped_rows=[Row(row_number=2), Row(row_number=3)]),
        )
        warnings = provider.validate(file)
        product_warnings = [item for item in warnings if item.get("row") in (2, 3)]
        self.assertEqual(len(product_warnings), 2)
        self.assertEqual(product_warnings[0]["message"], product_warnings[1]["message"])
        self.assertIn("Rows: 2–3 (2 rows).", product_warnings[0]["message"])
        _created, action = provider.import_row(importer, file.get_payloads_for_import()[2].doc)
        self.assertEqual(action, "Insert")
        self.assertEqual(len(database.records), 1)

    def test_duplicate_local_ids_and_existing_conflicts_are_blocked(self):
        module, frappe, database, _masters = load_provider()
        frappe.local.lang = "en"
        file = import_file(source(local_event_id="same"), source(local_event_id="same"))
        warnings = module.QCInspectionEventImportProvider().validate(file)
        self.assertTrue(any("duplicated" in item["message"] for item in warnings))

        first = module._analyze(import_file(source(local_event_id="existing")))[0][0]
        event = dict(first[2])
        event["name"] = "stored-event"
        database.records[event["name"]] = event
        conflict = module.QCInspectionEventImportProvider().validate(
            import_file(source(local_event_id="existing", quantity_delta=99))
        )
        self.assertTrue(any("different data" in item["message"] for item in conflict))

    def test_reimport_is_idempotent_and_duplicate_rows_keep_distinct_ids(self):
        module, _frappe, database, _masters = load_provider()
        file = import_file(source(), source())
        provider = module.QCInspectionEventImportProvider()
        importer = types.SimpleNamespace(
            import_type="Insert New Records", import_file=file,
            data_import=Row(name=None, skipped_rows=[]),
        )
        for payload in file.get_payloads_for_import():
            _created, action = provider.import_row(importer, payload.doc)
            self.assertEqual(action, "Insert")
        self.assertEqual(len(database.records), 2)

        provider = module.QCInspectionEventImportProvider()
        for payload in file.get_payloads_for_import():
            _stored, action = provider.import_row(importer, payload.doc)
            self.assertEqual(action, "Update")
        self.assertEqual(len(database.records), 2)

    def test_invalid_quantity_and_timestamp_are_row_warnings(self):
        module, frappe, _database, _masters = load_provider()
        frappe.local.lang = "en"
        warnings = module.QCInspectionEventImportProvider().validate(import_file(
            source(quantity_delta="1.5"),
            source(occurred_at="not-a-date"),
            source(synced_at=datetime(2065, 1, 1)),
        ))
        self.assertEqual({item["row"] for item in warnings}, {2, 3, 4})
        text = "\n".join(item["message"] for item in warnings)
        self.assertIn("integer", text)
        self.assertIn("Occurred At", text)
        self.assertIn("future", text)

    def test_import_schema_hides_generated_fields_and_allows_codes(self):
        module, _frappe, _database, _masters = load_provider()
        fields = {
            field["fieldname"]: field
            for field in module.QCInspectionEventImportProvider().get_import_fields()["fields"]
        }
        self.assertNotIn("event_uid", fields)
        self.assertNotIn("server_date_key", fields)
        self.assertEqual(fields["device"]["fieldtype"], "Data")
        self.assertEqual(fields["local_event_id"]["reqd"], 0)
        self.assertEqual(fields["synced_at"]["reqd"], 0)

    def test_insert_only_provider_and_analysis_are_cached(self):
        module, frappe, database, _masters = load_provider()
        update_file = import_file(source(), import_type="Update Existing Records")
        warning = module.QCInspectionEventImportProvider().validate(update_file)
        self.assertEqual(len(warning), 1)

        file = import_file(source(), source())
        importer = types.SimpleNamespace(
            import_type="Insert New Records", import_file=file,
            data_import=Row(name=None, skipped_rows=[]),
        )
        provider = module.QCInspectionEventImportProvider()
        with patch.object(module, "_analyze", wraps=module._analyze) as analyze:
            self.assertEqual(provider.validate(file), [])
            for payload in file.get_payloads_for_import():
                provider.import_row(importer, payload.doc)
        self.assertEqual(analyze.call_count, 1)
        self.assertEqual(len(database.records), 2)
        self.assertEqual(database.single_value_reads, 1)
        self.assertTrue(frappe.calls)

    def test_catalog_and_timezone_lookups_do_not_scale_per_row(self):
        module, frappe, database, _masters = load_provider()
        file = import_file(*(source() for _ in range(1_200)))
        prepared, warnings, _existing = module._analyze(file)
        self.assertEqual(len(prepared), 1_200)
        self.assertEqual(warnings, [])
        self.assertEqual(len(frappe.calls), 16)
        self.assertEqual(database.single_value_reads, 1)


if __name__ == "__main__":
    unittest.main()
