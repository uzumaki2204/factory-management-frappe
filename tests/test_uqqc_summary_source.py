"""UQQC source checks for the existing InspectionSummary contract."""

import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from factory_management.qcbrother_reporting.model import ReportQuery, ReportSourceError


ZONE = timezone(timedelta(hours=7))
DIMENSIONS = {
    "companyCode": "KT2", "companyName": "Kim Thành 2", "factoryCode": "F1",
    "sampleCode": "STYLE", "countryCode": "US", "countryName": "United States",
    "colorCode": "RED", "sizeCode": "S", "sizeName": "Small",
    "lineCode": "L1", "lineName": "Line 1",
}


def load_source(sql):
    frappe = types.ModuleType("frappe")
    frappe.db = types.SimpleNamespace(sql=sql)
    name = "factory_management.qcbrother_reporting._uqqc_under_test"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "factory_management/qcbrother_reporting/uqqc.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"frappe": frappe, name: module}):
        spec.loader.exec_module(module)
    return module


class UqqcSummarySourceTests(unittest.TestCase):
    def test_summary_reads_uqqc_and_spl_orders_with_existing_dto(self):
        defect = dict(DIMENSIONS, occurredAt=datetime(2026, 10, 5, 17),
                      eventNo="", deviceNo="abcQC2defQC1", defectCode="B21",
                      defectName="Defect", positionCode="PLC0024", positionName="Position",
                      quantity=1)
        passed = dict(defect, eventNo="PASS", defectCode="", defectName="",
                      positionCode="", positionName="")
        reworked = dict(passed, eventNo="REWORK")

        def database(statement, values, as_dict):
            self.assertTrue(as_dict)
            if "tabUQQC Inspection Event" in statement:
                if "e.event_kind = 'defect'" in statement:
                    return [defect, dict(defect)]
                return [passed, reworked]
            if "tabSPL Purchase Order Item" in statement:
                return [dict(DIMENSIONS, purchaseOrderId="old-po", poNumber="PO-A", orderQty=10),
                        dict(DIMENSIONS, purchaseOrderId="new-po", poNumber="PO-A", orderQty=10),
                        dict(DIMENSIONS, purchaseOrderId="eligible-po", poNumber="PO-B", orderQty=10)]
            if "tabSPL Purchase Order` po" in statement:
                return [dict(id="old-po", poNumber="PO-A", revisionNo="1",
                             status="Confirmed", documentStatus="New"),
                        dict(id="new-po", poNumber="PO-A", revisionNo="2",
                             status="Completed", documentStatus="Change"),
                        dict(id="eligible-po", poNumber="PO-B", revisionNo="10",
                             status="Confirmed", documentStatus="New")]
            self.fail("Unexpected database source")

        sql = Mock(side_effect=database)
        module = load_source(sql)
        query = ReportQuery.parse("2026-10-06", "2026-10-06", ZONE, 7)
        rows = module.UqqcSummaryService(module.UqqcRepository()).summary(query)
        self.assertEqual([(row["eventNo"], row["quantity"]) for row in rows],
                         [("", 2), ("PASS", 1), ("REWORK", 1)])
        self.assertTrue(all(row["deviceQc"] == "QC2" and row["poNumbers"] == "PO-B" for row in rows))
        self.assertTrue(all(row["occurredOn"] == "2026-10-06T00:00:00+07:00" for row in rows))
        self.assertTrue(all(row["factoryCode"] == "F1" for row in rows))
        self.assertEqual(sql.call_args_list[0].args[1][:2],
                         [datetime(2026, 10, 5, 17), datetime(2026, 10, 6, 17)])

    def test_filters_are_bound_and_source_errors_are_sanitized(self):
        sql = Mock(return_value=[])
        module = load_source(sql)
        query = ReportQuery.parse("2026-10-06", "2026-10-06", ZONE, 7,
                                  company_code="KT2", qc="qc2", sample_code="STYLE", event_no="PASS")
        self.assertEqual(module.UqqcRepository().events(query, quantity=True), [])
        statement, values = sql.call_args.args
        self.assertNotIn("STYLE", statement)
        self.assertIn("e.event_kind = %s", statement)
        self.assertEqual(values[-4:], ["KT2", "QC2", "STYLE", "pass"])
        sql.side_effect = RuntimeError("database credentials")
        with self.assertRaisesRegex(ReportSourceError, "^QCBROTHER_UQQC_UNAVAILABLE$"):
            module.UqqcRepository().events(query, quantity=True)


if __name__ == "__main__":
    unittest.main()
