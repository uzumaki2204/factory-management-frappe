"""Contract cases derived from the .NET QCBrother report behavior."""

import copy
import importlib.util
import json
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from factory_management.qcbrother_reporting.model import LegacyResolver, ReportInputError, ReportQuery, device_qc
from factory_management.qcbrother_reporting.orders import purchase_order_values
from factory_management.qcbrother_reporting.repository import ReportRepository
from factory_management.qcbrother_reporting.service import ReportService
from factory_management.qcbrother_reporting.sqlserver import ReportSourceError, SqlReader, SqlServer


ZONE = timezone(timedelta(hours=7))
COMPANY = "11111111-1111-1111-1111-111111111111"
LINE = dict(companyId=COMPANY, companyCode="KT", companyName="Công ty", lineCode="L1",
            lineName="Chuyền 1", factoryCode="F1")
DIMENSIONS = dict(companyCode="KT", companyName="Công ty", sampleCode="STYLE", countryCode="US",
                  countryName="Mỹ", colorCode="RED", sizeCode="S", sizeName="Nhỏ")


def query(max_days=7, **kwargs):
    return ReportQuery.parse("2026-10-06", "2026-10-06", ZONE, max_days, **kwargs)


def event(event_no="", quantity=1, **values):
    return dict(DIMENSIONS, occurredAt=datetime(2026, 10, 5, 17), deviceNo="001QC1KT",
                factoryCode="F1", lineCode="L1", lineName="Chuyền 1", defectCode="D1" if not event_no else "",
                defectName="Lỗi" if not event_no else "", positionCode="P1" if not event_no else "",
                positionName="Vị trí" if not event_no else "", eventNo=event_no, quantity=quantity) | values


def legacy(event_no="0001", **values):
    return dict(serialNo="001QC1KT", itemId="STYLE.US-Mỹ.RED.S-Nhỏ.L1-Chuyền 1",
                occurredAt=datetime(2026, 10, 6, 0, 30), eventNo=event_no,
                paramsJson=json.dumps([None, 999, "D1-Lỗi", None, None, None, "P1-Vị trí"])) | values


class FixtureRepository:
    def events(self, request, quantity=False, mode="summary"):
        rows = [event("PASS", 4), event("REWORK", 2)] if quantity else [event(quantity=3)]
        if request.event_no:
            rows = [row for row in rows if row["eventNo"] == request.event_no]
        return copy.deepcopy(rows)

    def legacy(self, request, mode):
        rows = [legacy(), legacy("0041")]
        if request.event_no:
            rows = [row for row in rows if row["eventNo"] == "0041"]
        return rows

    def lines(self):
        return [LINE]

    def order_details(self, keys):
        return [dict(DIMENSIONS, purchaseOrderId=str(index), poNumber=number, orderQty=amount)
                for index, number, amount in ((1, "PO-A", 100), (2, "PO-A", 20), (3, "PO-B", 30),
                                              (4, "PO-B", 7), (5, "PO-C", 11), (6, "PO-C", 12))]

    def order_revisions(self, numbers):
        return [dict(id=str(index), poNumber=number, revisionNo=revision, status=status, documentStatus=document)
                for index, number, revision, status, document in (
                    (1, "PO-A", "1", "Confirmed", "New"), (2, "PO-A", "2", "Completed", "Change"),
                    (3, "PO-B", "10", "Confirmed", "New"), (4, "PO-B", "2", "Confirmed", "New"),
                    (5, "PO-C", "1", "Confirmed", "New"), (6, "PO-C", "2", "Confirmed", "Cancel"))]


class QueryTests(unittest.TestCase):
    def test_ranges_are_required_reversed_and_inclusive(self):
        for maximum in (7, 31):
            end = "2026-10-07" if maximum == 7 else "2026-10-31"
            request = ReportQuery.parse(end, "2026-10-01", ZONE, maximum)
            self.assertEqual(request.begin.isoformat(), "2026-10-01")
            self.assertEqual(request.end.isoformat(), end)
        for begin, end, maximum, code in ((None, None, 7, "QCBROTHER_RANGE_REQUIRED"),
                ("bad", "2026-10-01", 7, "QCBROTHER_RANGE_INVALID"),
                ("2026-10-01", "2026-10-08", 7, "QCBROTHER_RANGE_MAX_7"),
                ("2026-10-01", "2026-11-01", 31, "QCBROTHER_RANGE_MAX_31")):
            with self.subTest(code=code), self.assertRaisesRegex(ReportInputError, code):
                ReportQuery.parse(begin, end, ZONE, maximum)

    def test_new_event_bounds_are_utc_but_legacy_bounds_are_local(self):
        self.assertEqual(query().bounds()[0], datetime(2026, 10, 5, 17))
        self.assertEqual(query().bounds(legacy=True)[0], datetime(2026, 10, 6))
        self.assertEqual(query().all_time().bounds(), (None, None))

    def test_company_uuid_and_first_qc_marker(self):
        with self.assertRaisesRegex(ReportInputError, "QCBROTHER_COMPANY_ID_INVALID"):
            query(company_id="bad")
        self.assertEqual(query(company_id="00000000-0000-0000-0000-000000000000").company_id, "")
        self.assertEqual(device_qc("abcQC2defQC1"), "QC2")
        self.assertEqual(device_qc("nothing"), "")


class LegacyTests(unittest.TestCase):
    def test_legacy_quantity_ignores_params_and_pass_clears_defect(self):
        resolver = LegacyResolver([LINE])
        row = resolver.resolve(legacy(), query(), summary=True)
        self.assertEqual((row["quantity"], row["defectCode"], row["positionName"]), (1, "D1", "Vị trí"))
        passed = resolver.resolve(legacy("0041"), query(), summary=True)
        self.assertEqual((passed["eventNo"], passed["defectCode"], passed["positionCode"]), ("PASS", "", ""))

    def test_line_name_disambiguates_company_before_filter(self):
        other = dict(LINE, companyId="22222222-2222-2222-2222-222222222222", companyCode="OTHER",
                     lineName="Other", factoryCode="F2")
        resolver = LegacyResolver([other, LINE])
        self.assertEqual(resolver.resolve(legacy(), query(company_id=COMPANY))["companyCode"], "KT")
        self.assertIsNone(resolver.resolve(legacy(), query(company_code="OTHER")))
        self.assertIsNone(resolver.resolve(legacy(itemId="STYLE.US.RED.S.L1"), query()))

    def test_company_id_and_serial_suffix_never_resolve_missing_line(self):
        self.assertIsNone(LegacyResolver([]).resolve(legacy(companyId=COMPANY), query()))

    def test_factory_ambiguity_returns_empty_without_dropping_company(self):
        resolver = LegacyResolver([LINE, dict(LINE, factoryCode="F2")])
        row = resolver.resolve(legacy(), query(), summary=True)
        self.assertEqual((row["companyCode"], row["factoryCode"]), ("KT", ""))


class ProjectionTests(unittest.TestCase):
    def test_summary_merges_sources_without_cross_source_deduplication(self):
        rows = ReportService(FixtureRepository()).summary(query())
        self.assertEqual({row["eventNo"]: row["quantity"] for row in rows}, {"": 4, "PASS": 5, "REWORK": 2})
        self.assertTrue(all(row["occurredOn"] == "2026-10-06T00:00:00+07:00" for row in rows))
        self.assertTrue(all(row["poNumbers"] == "PO-B" and row["factoryCode"] == "F1" for row in rows))

    def test_summary_event_filter_and_unknown_event(self):
        service = ReportService(FixtureRepository())
        self.assertEqual(service.summary(query(event_no="pass"))[0]["quantity"], 5)
        self.assertEqual(service.summary(query(event_no="rework"))[0]["quantity"], 2)
        self.assertEqual(service.summary(query(event_no="0041")), [])

    def test_po_latest_revision_status_differs_for_planned_and_summary(self):
        repository = FixtureRepository()
        self.assertEqual(purchase_order_values(repository, [DIMENSIONS]), {("STYLE", "US", "RED", "S"): "PO-B"})
        self.assertEqual(purchase_order_values(repository, [DIMENSIONS], planned=True),
                         {("STYLE", "US", "RED", "S"): 50})

    def test_aggregate_splits_serial_and_variant_but_shares_all_time_totals(self):
        class Repository(FixtureRepository):
            def events(self, request, quantity=False, mode="daily"):
                if mode == "totals":
                    return [event("PASS", 11), event("REWORK", 7)] if quantity else [event(quantity=5)]
                return ([event("PASS", 2, deviceNo="002QC1KT", colorCode="BLUE", sizeCode="M")]
                        if quantity else [event(quantity=3)])

            def legacy(self, request, mode):
                return [legacy("0041", quantity=50), legacy(quantity=7)] if mode == "totals" else []
        rows = ReportService(Repository()).aggregate(query(31))
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["serialNo"] for row in rows], ["001QC1KT", "002QC1KT"])
        self.assertTrue(all((row["totalPass"], row["totalRework"], row["totalDefect"]) == (61, 7, 12) for row in rows))
        self.assertEqual(rows[0]["occurredOn"], "2026-10-06T00:00:00+07:00")
        self.assertEqual([row["plannedQuantity"] for row in rows], [50, 0])
        self.assertNotIn("deviceNo", rows[0])
        self.assertNotIn("lineCode", rows[0])


class SqlBoundaryTests(unittest.TestCase):
    def test_filters_are_bound_parameters_and_company_filter_not_applied_to_legacy_sql(self):
        reader = Mock()
        reader.rows.return_value = []
        repository = ReportRepository(reader)
        request = query(company_id=COMPANY, sample_code="x' OR 1=1--", qc="QC%")
        repository.events(request)
        statement, parameters = reader.rows.call_args.args
        self.assertNotIn(request.sample_code, statement)
        self.assertIn(request.sample_code, parameters)
        self.assertIn("l.CompanyId = e.CompanyId", statement)
        repository.legacy(request)
        self.assertNotIn("CompanyId", reader.rows.call_args.args[0])

    def test_connection_quotes_secrets_and_errors_never_echo_them(self):
        source = SqlServer(dict(host="sql", database="db", user="reader", password="x};PWD=oops"))
        self.assertIn("PWD={x}};PWD=oops}", source._connection_string())
        connection = Mock()
        connection.cursor.return_value.execute.side_effect = RuntimeError("password=secret")
        with self.assertRaisesRegex(ReportSourceError, "^QCBROTHER_SQL_UNAVAILABLE$"):
            list(SqlReader(connection).rows("SELECT ?", [1]))
        with self.assertRaisesRegex(ReportSourceError, "QCBROTHER_SQL_QUERY_INVALID"):
            list(SqlReader(connection).rows("DELETE FROM source"))


class EndpointTests(unittest.TestCase):
    def load_endpoint(self, denied=False):
        frappe = types.ModuleType("frappe")
        frappe._ = lambda key: key
        frappe.ValidationError = type("ValidationError", (Exception,), {})
        frappe.whitelist = lambda **kwargs: lambda function: function
        frappe.conf = {}
        frappe.db = types.SimpleNamespace(get_single_value=lambda *args: "Asia/Ho_Chi_Minh")
        frappe.throw = lambda message, kind: (_ for _ in ()).throw(kind(message))
        access = types.ModuleType("factory_management.api_access")
        access.require_report_access = Mock(side_effect=PermissionError if denied else None)
        with patch.dict(sys.modules, {"frappe": frappe, "factory_management.api_access": access}):
            spec = importlib.util.spec_from_file_location("qcbrother_endpoint_under_test", ROOT / "factory_management/qcbrother_reports.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def test_permission_denial_precedes_uqqc_query(self):
        module = self.load_endpoint(denied=True)
        with patch.object(module, "UqqcRepository") as source, self.assertRaises(PermissionError):
            module.inspection_summary("2026-10-06", "2026-10-06")
        source.assert_not_called()

    def test_input_and_upstream_errors_have_separate_status_codes(self):
        module = self.load_endpoint()
        with patch.object(module, "ZoneInfo", return_value=ZONE):
            with self.assertRaises(module.ReportValidationError) as invalid:
                module.inspection_summary()
            self.assertEqual(invalid.exception.http_status_code, 400)
            with patch.object(module, "UqqcRepository", side_effect=ReportSourceError("QCBROTHER_UQQC_UNAVAILABLE")):
                with self.assertRaises(module.ReportUnavailableError) as unavailable:
                    module.inspection_summary("2026-10-06", "2026-10-06")
            self.assertEqual(unavailable.exception.http_status_code, 503)
            self.assertEqual(str(unavailable.exception), "QCBROTHER_UQQC_UNAVAILABLE")

    def test_company_uuid_uses_sql_only_to_resolve_company_code(self):
        module = self.load_endpoint()
        reader = Mock()
        reader.rows.return_value = [{"companyCode": "KT2"}]
        source = Mock()
        source.connect.return_value.__enter__ = Mock(return_value=reader)
        source.connect.return_value.__exit__ = Mock(return_value=False)
        with patch.object(module, "ZoneInfo", return_value=ZONE), \
                patch.object(module, "SqlServer", return_value=source) as sql, \
                patch.object(module, "UqqcRepository") as repository, \
                patch.object(module, "UqqcReportService") as service:
            service.return_value.summary.return_value = []
            module.inspection_summary("2026-10-06", "2026-10-06",
                                      companyId=COMPANY)
        sql.assert_called_once()
        self.assertIn("dbo.Companies", reader.rows.call_args.args[0])
        repository.assert_called_once_with("KT2")

    def test_aggregate_uses_frappe_without_sql_server(self):
        module = self.load_endpoint()
        with patch.object(module, "ZoneInfo", return_value=ZONE), \
                patch.object(module, "SqlServer") as sql, \
                patch.object(module, "UqqcRepository") as repository, \
                patch.object(module, "UqqcReportService") as service:
            service.return_value.aggregate.return_value = [{"pass": 1}]
            self.assertEqual(module.inspection_aggregate("2026-10-06", "2026-10-06"), [{"pass": 1}])
            with self.assertRaises(module.ReportValidationError) as invalid:
                module.inspection_aggregate("2026-10-06", "2026-10-06", companyId=COMPANY)
        sql.assert_not_called()
        repository.assert_called_once_with()
        self.assertEqual(invalid.exception.http_status_code, 400)
        self.assertEqual(str(invalid.exception), "QCBROTHER_AGGREGATE_COMPANY_ID_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
