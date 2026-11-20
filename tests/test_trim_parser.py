"""Checks for the two-row Trim report header and material fallback data."""

import unittest
from io import BytesIO

from openpyxl import Workbook

from factory_management.trim.parser import HEADERS, WorkbookError, parse_workbook


def workbook_bytes(change=None):
    book = Workbook()
    sheet = book.active
    sheet.title = "ExcelOut(Trim)"
    sheet.append(["Trim Order Info"])
    sheet.append(list(HEADERS))
    values = [None] * len(HEADERS)
    values[0] = "T-001"
    values[1] = 1
    values[2] = 2027
    values[9] = "Cancel"
    values[20] = "WOV0001"
    values[21] = "0012"
    values[22] = "Supplier material"
    values[30] = "0491618"
    values[36] = "00"
    values[39] = "003"
    values[41] = 4512
    if change:
        change(values)
    sheet.append(values)
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


class TrimParserTests(unittest.TestCase):
    def test_preserves_codes_and_cancelled_order_with_blank_trim_fields(self):
        rows = parse_workbook(workbook_bytes(), "trim.xlsx")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["header"]["document_status"], "Cancel")
        self.assertEqual(rows[0]["header"]["revision_no"], "1")
        self.assertEqual(rows[0]["item"]["item_code"], "0491618")
        self.assertEqual(rows[0]["item"]["supplier_raw_material_code"], "0012")
        self.assertEqual(rows[0]["item"]["trim_item_no"], "")
        self.assertEqual(rows[0]["item"]["order_qty"], 4512)

    def test_rejects_fractional_quantity(self):
        with self.assertRaisesRegex(WorkbookError, "Invalid integer"):
            parse_workbook(workbook_bytes(lambda values: values.__setitem__(41, 1.5)), "trim.xlsx")

    def test_rejects_wrong_sheet_and_format(self):
        with self.assertRaisesRegex(WorkbookError, "Only .xlsx"):
            parse_workbook(workbook_bytes(), "trim.xls")
        with self.assertRaisesRegex(WorkbookError, "Invalid Excel"):
            parse_workbook(b"invalid", "trim.xlsx")


if __name__ == "__main__":
    unittest.main()
