"""Transaction boundaries and progress for Trim imports."""

import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch


def load_service(frappe):
    utils = types.ModuleType("frappe.utils")
    utils.get_datetime = lambda value: value
    utils.now_datetime = datetime.now
    frappe.__path__ = []
    with patch.dict(sys.modules, {"frappe": frappe, "frappe.utils": utils}):
        path = Path(__file__).resolve().parents[1] / "factory_management/trim/service.py"
        spec = importlib.util.spec_from_file_location("trim_service_batch_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class TrimImportBatchTests(unittest.TestCase):
    def setUp(self):
        self.frappe = types.ModuleType("frappe")
        self.frappe.db = MagicMock()
        self.frappe.get_traceback = Mock(return_value="traceback")
        self.frappe.log_error = Mock()
        self.lock = MagicMock()
        self.lock.acquire.return_value = True
        cache = MagicMock()
        cache.lock.return_value = self.lock
        self.frappe.cache = Mock(return_value=cache)
        self.run = types.SimpleNamespace(
            status="Queued", imported_orders=0, imported_items=0, failed_orders=0,
            error_detail="", message="", completed_at=None,
            save=Mock(), reload=Mock(),
        )
        self.frappe.get_doc = Mock(return_value=self.run)
        self.service = load_service(self.frappe)

    @staticmethod
    def rows(count):
        return [{"header": {"order_no": f"T-{index}", "revision_no": "1"}}
                for index in range(count)]

    def test_commits_every_fifty_orders_and_keeps_per_order_failure(self):
        def import_group(group):
            if group[0]["header"]["order_no"] == "T-70":
                raise ValueError("bad order")
            return 2

        with patch.object(self.service, "_load_snapshot", return_value=self.rows(101)), \
             patch.object(self.service, "_import_group", side_effect=import_group):
            self.service.execute_import("run-1", "token")

        self.assertEqual(self.frappe.db.commit.call_count, 4)
        self.assertEqual(self.frappe.db.savepoint.call_count, 101)
        self.frappe.db.rollback.assert_called_once_with(save_point="trim_70")
        self.assertEqual((self.run.imported_orders, self.run.imported_items,
                          self.run.failed_orders), (100, 200, 1))
        self.assertEqual(self.run.status, "Partial Success")
        self.assertIn("T-70 / 1", self.run.error_detail)

    def test_fatal_batch_failure_restores_last_committed_progress(self):
        def savepoint(name):
            if name == "trim_52":
                raise RuntimeError("database error")

        def reload_run():
            self.run.imported_orders = 50
            self.run.imported_items = 50
            self.run.failed_orders = 0

        self.frappe.db.savepoint.side_effect = savepoint
        self.run.reload.side_effect = reload_run
        with patch.object(self.service, "_load_snapshot", return_value=self.rows(55)), \
             patch.object(self.service, "_import_group", return_value=1):
            self.service.execute_import("run-1", "token")

        self.frappe.db.rollback.assert_called_once_with()
        self.assertEqual((self.run.imported_orders, self.run.imported_items), (50, 50))
        self.assertEqual(self.run.status, "Failed")
        self.assertEqual(self.frappe.db.commit.call_count, 3)


if __name__ == "__main__":
    unittest.main()
