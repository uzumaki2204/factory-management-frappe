"""Run on a disposable Frappe test site after installing the app."""

import uuid
import unittest

try:
    import frappe
    from frappe.tests.utils import FrappeTestCase
    from factory_management.spl_po import parser, service
except ImportError:
    frappe = None
    FrappeTestCase = unittest.TestCase


@unittest.skipIf(frappe is None, "Frappe test site is required")
class SplPoSiteTests(FrappeTestCase):
    def test_upsert_replaces_items_without_duplicate_po(self):
        suffix = uuid.uuid4().hex[:10]
        customer = frappe.get_doc({
            "doctype": "Customer", "customer_code": "SPL-" + suffix,
            "customer_name": "SPL Test " + suffix, "is_active": 1,
        }).insert(ignore_permissions=True)
        settings = frappe._dict(customer=customer.name)
        row = {name: "" for name in parser.TEXT}
        row.update({name: None for name in parser.DATES})
        row.update({
            "po_number": "TEST-" + suffix, "revision_no": "1", "planning_year": 2026,
            "planning_season_code": "SS", "market_code": "07", "business_unit": "Market 07",
            "sample_code": "P" + suffix, "item_name": "Test Product",
            "item_code": "I" + suffix, "color_code": "C" + suffix,
            "color_name": "Test Color", "size_code": "S" + suffix,
            "size_name": "Size " + suffix, "order_qty": 2, "row_number": 3,
        })
        cache = service._master_cache([row], customer.name)
        self.assertEqual(service._import_group(settings, [row], cache, "test.xlsx"), 1)
        source_key = frappe.db.get_value("SPL Purchase Order", {"po_number": row["po_number"]}, "source_key")
        row["order_qty"] = 5
        self.assertEqual(service._import_group(settings, [row], cache, "test.xlsx"), 1)
        orders = frappe.get_all("SPL Purchase Order", filters={"source_key": source_key}, fields=["name"])
        self.assertEqual(len(orders), 1)
        order = frappe.get_doc("SPL Purchase Order", orders[0].name)
        self.assertEqual(order.total_quantity, 5)
        self.assertEqual(len(order.items), 1)
        self.assertEqual(order.items[0].order_qty, 5)

    def test_duplicate_item_is_rejected_before_import(self):
        row = {"po_number": "PO", "revision_no": "1", "sample_code": "ABC",
               "color_code": "09", "size_code": "M", "market_code": "07", "row_number": 3}
        other = {**row, "row_number": 4}
        self.assertIn(4, service._validate([row, other]))
