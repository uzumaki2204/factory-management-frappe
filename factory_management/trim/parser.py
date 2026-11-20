"""Parse SPL ExcelOut(Trim) workbooks without a Frappe dependency."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

SHEET = "ExcelOut(Trim)"
MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 50_000
HEADERS = (
    "Order No.", "Revision No.", "Year", "Planning Ssn", "Global Business Unit",
    "Business Unit", "Item Brand", "Department", "Revised Date", "Document Status",
    "Answered Status", "Vendor Person in Charge", "Decision Date", "Payment Terms",
    "Contracted ETD", "ETA WH", "Approver", "Approval Date", "Order Conditions",
    "Remark", "Raw Material Code(FR)", "Supplier Raw Material Code",
    "Supplier Raw Material", "Vendor Code", "Vendor", "Management Factory Code",
    "Management Factory", "Branch Factory Code", "Branch Factory", "Order Plan Number",
    "Item Code", "Item", "Representative Sample Code", "Sample Code", "Contracted ETD",
    "ETA WH", "Color Code", "Color", "Pattern Dimension Code", "Size Code", "Size",
    "Order Qty(pcs)", "Arrangement By", "Trim Description", "Trim Item No.", "Trim Supplier",
)
HEADER_TEXT = {
    "order_no": 0, "revision_no": 1, "planning_season": 3,
    "global_business_unit": 4, "business_unit": 5, "item_brand": 6,
    "department": 7, "document_status": 9, "answered_status": 10,
    "vendor_person_in_charge": 11, "payment_terms": 13, "approver": 16,
    "order_conditions": 18, "remark": 19, "raw_material_code": 20,
    "supplier_raw_material_code": 21, "supplier_raw_material": 22,
    "vendor_code": 23, "vendor": 24, "management_factory_code": 25,
    "management_factory": 26, "branch_factory_code": 27, "branch_factory": 28,
}
HEADER_DATES = {"revised_date": 8, "decision_date": 12, "contracted_etd": 14,
                "eta_wh": 15, "approval_date": 17}
ITEM_TEXT = {
    "order_plan_number": 29, "item_code": 30, "item_name": 31,
    "representative_sample_code": 32, "sample_code": 33, "color_code": 36,
    "color": 37, "pattern_dimension_code": 38, "size_code": 39,
    "size": 40, "arrangement_by": 42, "trim_description": 43,
    "trim_item_no": 44, "trim_supplier": 45,
}
ITEM_DATES = {"contracted_etd": 34, "eta_wh": 35}


class WorkbookError(ValueError):
    def __init__(self, code, row=None, column=None):
        self.code = code
        self.row = row
        self.column = column
        super().__init__(f"{code}" + (f" at row {row}, {column}" if row else ""))


def _text(value):
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _date(value, row, column, datetime_field=False):
    if value is None or _text(value) == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S") if datetime_field else value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat() + " 00:00:00" if datetime_field else value.isoformat()
    raw = _text(value)
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(raw, pattern)
            return parsed.strftime("%Y-%m-%d %H:%M:%S") if datetime_field else parsed.date().isoformat()
        except ValueError:
            pass
    raise WorkbookError("Invalid date", row, column)


def _integer(value, row, column):
    raw = _text(value).replace(",", "")
    if not raw:
        raise WorkbookError("Required number is missing", row, column)
    try:
        number = Decimal(raw)
        if number != number.to_integral_value():
            raise InvalidOperation
        return int(number)
    except (InvalidOperation, ValueError):
        raise WorkbookError("Invalid integer", row, column) from None


def parse_workbook(content, filename):
    if not content or len(content) > MAX_BYTES:
        raise WorkbookError("File must be an Excel workbook under 20 MB")
    if Path(filename).suffix.lower() != ".xlsx":
        raise WorkbookError("Only .xlsx workbooks are supported")
    from openpyxl import load_workbook

    try:
        book = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise WorkbookError("Invalid Excel workbook") from None
    try:
        sheet = next((book[name] for name in book.sheetnames if name.lower() == SHEET.lower()), None)
        if sheet is None:
            raise WorkbookError(f"Sheet {SHEET} is missing")
        iterator = sheet.iter_rows(values_only=True)
        next(iterator, ())  # report caption row
        actual = tuple(" ".join(_text(value).split()) for value in next(iterator, ()))
        if actual[:len(HEADERS)] != HEADERS:
            raise WorkbookError("Workbook columns do not match the Trim report")
        rows = []
        for row_number, values in enumerate(iterator, start=3):
            def cell(index):
                return values[index] if index < len(values) else None
            if not any(value is not None and _text(value) for value in values):
                continue
            if len(rows) >= MAX_ROWS:
                raise WorkbookError("Workbook exceeds 50,000 data rows")
            if not _text(cell(0)):
                raise WorkbookError("Order No. is required", row_number, "Order No.")
            header = {name: _text(cell(index)) for name, index in HEADER_TEXT.items()}
            header.update({name: _date(cell(index), row_number, HEADERS[index], name == "revised_date")
                           for name, index in HEADER_DATES.items()})
            header["planning_year"] = _integer(cell(2), row_number, "Year")
            item = {name: _text(cell(index)) for name, index in ITEM_TEXT.items()}
            item.update({name: _date(cell(index), row_number, HEADERS[index])
                         for name, index in ITEM_DATES.items()})
            item["order_qty"] = _integer(cell(41), row_number, "Order Qty(pcs)")
            if not item["item_code"] or not header["raw_material_code"]:
                raise WorkbookError("Item Code and Raw Material Code(FR) are required", row_number)
            item["raw_material_code"] = header["raw_material_code"]
            item["supplier_raw_material_code"] = header["supplier_raw_material_code"]
            item["supplier_raw_material"] = header["supplier_raw_material"]
            rows.append({"row_number": row_number, "header": header, "item": item})
        if not rows:
            raise WorkbookError("Workbook contains no Trim orders")
        return rows
    finally:
        book.close()
