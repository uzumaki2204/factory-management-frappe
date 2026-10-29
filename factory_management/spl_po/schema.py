"""App-owned SPL DocType definitions shared by install and metadata snapshots."""


def f(name, label, kind="Data", options=None, **extra):
    value = {"fieldname": name, "label": label, "fieldtype": kind}
    if options:
        value["options"] = options
    value.update(extra)
    return value


HEADER = [
    f("source_key", "Source Key", reqd=1, unique=1, read_only=1),
    f("customer", "Customer", "Link", "Customer", reqd=1, in_list_view=1),
    f("po_number", "PO Number", reqd=1, in_list_view=1),
    f("revision_no", "Revision No", in_list_view=1),
    f("production_season", "Production Season", "Link", "Production Season"),
    f("market", "Market", "Link", "Market"),
    f("order_date", "Order Date", "Date"),
    f("delivery_date", "Delivery Date", "Date"),
    f("ship_date", "Ship Date", "Date"),
    f("total_quantity", "Total Quantity", "Int", read_only=1),
    f("planning_year", "Planning Year", "Int"),
    f("planning_season_code", "Planning Season Code"),
    f("global_business_unit", "Global Business Unit"),
    f("business_unit", "Business Unit"),
    f("item_brand", "Item Brand"),
    f("department", "Department"),
    f("revised_date", "Revised Date", "Date"),
    f("document_status_external", "Document Status External"),
    f("approver", "Approver"),
    f("approval_date", "Approval Date", "Date"),
    f("deadline_date", "Deadline Date", "Date"),
    f("answered_status_external", "Answered Status External"),
    f("decision_date", "Decision Date", "Date"),
    f("sales_contract_no", "Sales Contract No"),
    f("bill_to_name", "Bill To Name"),
    f("bill_to_address", "Bill To Address", "Small Text"),
    f("bill_to_telephone", "Bill To Telephone"),
    f("bill_to_person_in_charge", "Bill To Person In Charge"),
    f("incoterms", "Incoterms"),
    f("transportation_method", "Transportation Method"),
    f("payment_terms", "Payment Terms"),
    f("payment_currency", "Payment Currency"),
    f("order_conditions", "Order Conditions", "Small Text"),
    f("order_plan_number", "Order Plan Number"),
    f("contracted_etd", "Contracted ETD", "Date"),
    f("eta_wh", "ETA WH", "Date"),
    f("imported_at", "Imported At", "Datetime", read_only=1),
    f("last_source_file_path", "Last Source File Path", "Small Text"),
    f("status", "PO Status", "Select", "Draft\nConfirmed\nIn Progress\nCompleted\nCancelled", default="Confirmed"),
    f("note", "Note", "Small Text"),
    f("items", "Items", "Table", "SPL Purchase Order Item"),
]

ITEM = [
    f("product", "Product", "Link", "Product", reqd=1, in_list_view=1),
    f("product_variant", "Product Variant", "Link", "Product Variant"),
    f("market", "Market", "Link", "Market"),
    f("product_color", "Product Color", "Link", "Product Color", reqd=1, in_list_view=1),
    f("size", "Size", "Link", "ProductSize", reqd=1, in_list_view=1),
    f("order_qty", "Order Qty", "Int", reqd=1, in_list_view=1),
    f("unit_price", "Unit Price", "Currency"),
    f("currency", "Currency"),
    f("import_line_key", "Import Line Key", read_only=1),
    f("item_code", "Item Code"),
    f("item_name", "Item Name"),
    f("pattern_dimension_code", "Pattern Dimension Code"),
    f("barcode", "Barcode"),
    f("sku", "SKU"),
    f("sku_code_for_shipping", "SKU Code For Shipping"),
    f("sample_code", "Sample Code"),
    f("representative_sample_code", "Representative Sample Code"),
    f("allocation_order_number", "Allocation Order Number"),
    f("original_sales_price_text", "Original Sales Price Text"),
    f("external_remark", "External Remark", "Small Text"),
    f("note", "Note", "Small Text"),
    f("source_row_number", "Source Row Number", "Int"),
]

SETTINGS = [
    f("base_url", "SPL Base URL", default="https://spl.fastretailing.com", reqd=1),
    f("spl_user_id", "SPL User ID", reqd=1),
    f("spl_password", "SPL Password", "Password"),
    f("client_certificate", "Client Certificate", "Link", "File"),
    f("certificate_password", "Certificate Password", "Password"),
    f("customer", "Customer", "Link", "Customer", reqd=1),
    f("auto_enabled", "Automatic Import Enabled", "Check", default="0"),
    f("schedule_times", "Schedule Times", default=""),
    f("schedule_timezone", "Schedule Time Zone", default="Asia/Ho_Chi_Minh"),
    f("request_timeout_seconds", "Request Timeout Seconds", "Int", default="120"),
    f("mode", "Mode", default="01"),
    f("answer_status_id", "Answer Status ID", default="0003"),
    f("item_brand_id", "Item Brand ID", default="010"),
    f("year_season_ids", "Year Season IDs", default="20252,20261,20262,20271"),
    f("management_factory_id", "Management Factory ID", default="015J"),
    f("document_status_ids", "Document Status IDs", default="0001,0002,0003,0004"),
    f("report_offset", "Report Offset", "Int", default="0"),
]

RUN = [
    f("status", "Status", "Select", "Queued\nRunning\nPreview Ready\nSuccess\nPartial Success\nFailed\nExpired", in_list_view=1),
    f("trigger_source", "Trigger Source", "Select", "Manual\nScheduled\nUpload\nConnection Test", in_list_view=1),
    f("requested_by", "Requested By", "Link", "User"),
    f("schedule_slot", "Schedule Slot", unique=1),
    f("started_at", "Started At", "Datetime", in_list_view=1),
    f("completed_at", "Completed At", "Datetime"),
    f("snapshot_token", "Snapshot Token", read_only=1),
    f("snapshot_path", "Snapshot Path", read_only=1, hidden=1),
    f("snapshot_expires_at", "Snapshot Expires At", "Datetime"),
    f("source_file_path", "Source File Path", "Small Text"),
    f("total_rows", "Total Rows", "Int"),
    f("total_orders", "Total Orders", "Int"),
    f("imported_orders", "Imported Orders", "Int"),
    f("imported_items", "Imported Items", "Int"),
    f("failed_orders", "Failed Orders", "Int"),
    f("missing_masters", "Missing Masters", "Int"),
    f("message", "Message", "Small Text"),
    f("error_detail", "Error Detail", "Long Text"),
]

TYPES = {
    "SPL Purchase Order": HEADER,
    "SPL Purchase Order Item": ITEM,
    "SPL Import Settings": SETTINGS,
    "SPL Import Run": RUN,
}
