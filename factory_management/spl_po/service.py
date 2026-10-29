"""Background preview and per-order transactional SPL import."""

import gzip
import hashlib
import json
import os
import secrets
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import frappe
from frappe.utils import get_datetime, now_datetime

from factory_management.spl_po.gateway import GatewayError, fetch_report
from factory_management.spl_po.messages import message
from factory_management.spl_po.parser import (MAX_BYTES, WorkbookError, normalize_currency,
                                              parse_unit_price, parse_workbook)

PREVIEW_MINUTES = 15


def _error(exc):
    if isinstance(exc, WorkbookError):
        return message(exc.code, **exc.context)
    if isinstance(exc, GatewayError):
        return message(str(exc))
    # Avoid leaking server paths, credentials, or SPL responses to run history.
    return message("SPL_IMPORT_FAILED")


def _settings():
    settings = frappe.get_single("SPL Import Settings")
    if not settings.customer or not frappe.db.exists("Customer", settings.customer):
        raise WorkbookError("SPL_CUSTOMER_REQUIRED")
    return settings


def _new_run(trigger):
    doc = frappe.get_doc({
        "doctype": "SPL Import Run", "status": "Queued", "trigger_source": trigger,
        "requested_by": frappe.session.user if frappe.session.user != "Guest" else "Administrator",
        "started_at": now_datetime(),
    })
    doc.insert(ignore_permissions=True)
    return doc


def queue_preview(file_url=None, connection_only=False):
    run = _new_run("Connection Test" if connection_only else ("Upload" if file_url else "Manual"))
    frappe.enqueue("factory_management.spl_po.service.prepare_preview", queue="long",
                   timeout=3600, enqueue_after_commit=True, job_name=f"spl-po-preview-{run.name}",
                   run_name=run.name, file_url=file_url, connection_only=connection_only)
    return run.name


def _upload_content(file_url):
    file_name = frappe.db.get_value("File", {"file_url": file_url, "is_private": 1}, "name")
    if not file_name:
        raise WorkbookError("SPL_UPLOAD_PRIVATE_REQUIRED")
    file_doc = frappe.get_doc("File", file_name)
    path = Path(file_doc.get_full_path()).resolve()
    private_root = Path(frappe.get_site_path("private")).resolve()
    if not path.is_relative_to(private_root) or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise WorkbookError("SPL_FILE_SIZE_INVALID")
    return path.read_bytes(), file_doc.file_name


def _snapshot_path(token):
    folder = Path(frappe.get_site_path("private", "files", "spl_po"))
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)
    return folder / f"{token}.json.gz"


def _save_snapshot(rows, customer):
    token = secrets.token_urlsafe(32)
    path = _snapshot_path(token)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb") as output:
            output.write(json.dumps({"customer": customer, "rows": rows},
                                    ensure_ascii=False).encode("utf-8"))
    return token, str(path)


def _load_snapshot(run, token):
    if not token or not secrets.compare_digest(token, run.snapshot_token or ""):
        raise WorkbookError("SPL_PREVIEW_INVALID")
    expiry = run.snapshot_expires_at
    if not expiry or get_datetime(expiry) < now_datetime():
        raise WorkbookError("SPL_PREVIEW_EXPIRED")
    path = _snapshot_path(token)
    if str(path) != run.snapshot_path or not path.is_file():
        raise WorkbookError("SPL_PREVIEW_INVALID")
    with gzip.open(path, "rt", encoding="utf-8") as source:
        return json.load(source)


def _missing_masters(rows, cache):
    missing = set()
    for row in rows:
        candidates = [
            ("Market", row["market_code"]), ("Product", row["sample_code"]),
            ("Product Color", row["color_code"]), ("ProductSize", row["size_code"]),
        ]
        if row["planning_year"] and row["planning_season_code"]:
            candidates.append(("Production Season", f"{row['planning_year']}{row['planning_season_code']}"))
        for doctype, code in candidates:
            if code.upper() not in cache[doctype]:
                missing.add((doctype, code.upper()))
        product = cache["Product"].get(row["sample_code"].upper())
        market = cache["Market"].get(row["market_code"].upper())
        color = cache["Product Color"].get(row["color_code"].upper())
        size = cache["ProductSize"].get(row["size_code"].upper())
        key = (product.name, market.name, color.name, size.name) if all((product, market, color, size)) else None
        if not key or key not in cache["Product Variant"]:
            missing.add(("Product Variant", "/".join((row["sample_code"], row["market_code"],
                                                       row["color_code"], row["size_code"])).upper()))
    return missing


def _row_missing(row, missing):
    candidates = (
        ("Market", row["market_code"].upper()),
        ("Product", row["sample_code"].upper()),
        ("Product Color", row["color_code"].upper()),
        ("ProductSize", row["size_code"].upper()),
        ("Production Season", f"{row['planning_year']}{row['planning_season_code']}".upper()),
        ("Product Variant", "/".join((row["sample_code"], row["market_code"],
                                      row["color_code"], row["size_code"])).upper()),
    )
    return [message("SPL_MASTER_WILL_CREATE", doctype=doctype, code=code)
            for doctype, code in candidates if (doctype, code) in missing]


def _group(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["po_number"], row["revision_no"])].append(row)
    return groups


def _validate(rows):
    errors = {}
    for key, group in _group(rows).items():
        seen = set()
        markets = set()
        for row in group:
            markets.add(row["market_code"].upper())
            item_key = (row["sample_code"].upper(), row["color_code"].upper(), row["size_code"].upper())
            if item_key in seen:
                errors[row["row_number"]] = message("SPL_DUPLICATE_ITEM", po=key[0], revision=key[1])
            seen.add(item_key)
        if len(markets) > 1:
            for row in group:
                errors[row["row_number"]] = message("SPL_MARKET_CONFLICT", po=key[0], revision=key[1])
    return errors


def prepare_preview(run_name, file_url=None, connection_only=False):
    run = frappe.get_doc("SPL Import Run", run_name)
    run.status = "Running"
    run.save(ignore_permissions=True)
    frappe.db.commit()
    try:
        settings = _settings()
        if file_url:
            content, source_path = _upload_content(file_url)
        else:
            content, source_path = fetch_report(settings, connection_only=connection_only)
        if connection_only:
            run.status = "Success"
            run.message = message("SPL_CONNECTION_OK")
        else:
            rows = parse_workbook(content, source_path)
            if not rows:
                raise WorkbookError("SPL_NO_ROWS")
            cache = _master_cache(rows, settings.customer)
            errors = _validate(rows)
            missing = _missing_masters(rows, cache)
            for row in rows:
                row["preview_error"] = errors.get(row["row_number"])
                row["preview_warnings"] = _row_missing(row, missing)
            token, path = _save_snapshot(rows, settings.customer)
            run.snapshot_token = token
            run.snapshot_path = path
            run.snapshot_expires_at = now_datetime() + timedelta(minutes=PREVIEW_MINUTES)
            run.source_file_path = source_path
            run.total_rows = len(rows)
            run.total_orders = len(_group(rows))
            run.missing_masters = len(missing)
            run.status = "Preview Ready"
            run.message = message("SPL_PREVIEW_READY")
    except (WorkbookError, GatewayError) as exc:
        run.status = "Failed"
        run.message = _error(exc)
    except Exception:
        run.status = "Failed"
        run.message = message("SPL_IMPORT_FAILED")
    run.completed_at = now_datetime()
    run.save(ignore_permissions=True)
    frappe.db.commit()


def preview_page(run_name, token, page=1, page_size=100):
    run = frappe.get_doc("SPL Import Run", run_name)
    if run.status != "Preview Ready":
        raise WorkbookError("SPL_PREVIEW_INVALID")
    data = _load_snapshot(run, token)
    rows = data["rows"]
    page = max(1, int(page))
    page_size = max(1, min(200, int(page_size)))
    start = (page - 1) * page_size
    shown = rows[start:start + page_size]
    shown_numbers = {row["row_number"] for row in shown}
    group_rows = {}
    for key, group in _group(rows).items():
        encoded = json.dumps(key, ensure_ascii=False, separators=(",", ":"))
        if any(row["row_number"] in shown_numbers for row in group):
            group_rows[encoded] = [row["row_number"] for row in group]
    result = []
    for row in shown:
        result.append({
            "row_number": row["row_number"], "po_number": row["po_number"],
            "revision_no": row["revision_no"], "sample_code": row["sample_code"],
            "market_code": row["market_code"], "color_code": row["color_code"],
            "size_code": row["size_code"], "order_qty": row["order_qty"],
            "error": row.get("preview_error"),
            "warnings": row.get("preview_warnings") or [],
            "group_key": json.dumps([row["po_number"], row["revision_no"]],
                                    ensure_ascii=False, separators=(",", ":")),
        })
    return {"rows": result, "total_rows": len(rows), "total_orders": len(_group(rows)),
            "page": page, "page_size": page_size,
            "errors": sum(bool(row.get("preview_error")) for row in rows),
            "expires_at": run.snapshot_expires_at, "missing_masters": run.missing_masters or 0,
            "group_rows": group_rows}


def queue_import(run_name, token, selected_rows, excluded_rows=None):
    source = frappe.get_doc("SPL Import Run", run_name)
    data = _load_snapshot(source, token)
    if source.status != "Preview Ready" or data["customer"] != _settings().customer:
        raise WorkbookError("SPL_PREVIEW_INVALID")
    available = {row["row_number"] for row in data["rows"]}
    try:
        excluded = {int(number) for number in (excluded_rows or [])}
        selected = (available - excluded if selected_rows == "all"
                    else {int(number) for number in selected_rows})
    except (TypeError, ValueError):
        raise WorkbookError("SPL_SELECTION_INVALID") from None
    if selected_rows == "all":
        if not excluded.issubset(available):
            raise WorkbookError("SPL_SELECTION_INVALID")
    if not selected or not selected.issubset(available):
        raise WorkbookError("SPL_SELECTION_INVALID")
    # A PO is the transaction boundary. Partial selection within it is forbidden.
    for group in _group(data["rows"]).values():
        numbers = {row["row_number"] for row in group}
        if numbers & selected and not numbers <= selected:
            raise WorkbookError("SPL_SELECTION_INCOMPLETE")
    run = _new_run("Manual")
    run.snapshot_token = token
    run.snapshot_path = source.snapshot_path
    # The 15-minute decision window closes on the preview; a confirmed job may
    # wait in the long queue without losing its exact, immutable snapshot.
    run.snapshot_expires_at = now_datetime() + timedelta(hours=2)
    run.source_file_path = source.source_file_path
    run.save(ignore_permissions=True)
    frappe.enqueue("factory_management.spl_po.service.execute_import", queue="long",
                   timeout=3600, enqueue_after_commit=True, job_name=f"spl-po-import-{run.name}",
                   run_name=run.name, token=token, selected_rows=sorted(selected))
    return run.name


def _lookup(doctype, code_field, codes, extra_fields=()):
    if not codes:
        return {}
    index = {}
    for batch in _batches(sorted(codes)):
        records = frappe.get_all(doctype, filters={code_field: ["in", batch]},
                                 fields=["name", code_field, *extra_fields], limit_page_length=0)
        for record in records:
            code = str(record.get(code_field) or "").upper()
            if code in index:
                raise WorkbookError("SPL_MASTER_AMBIGUOUS", doctype=doctype, code=code)
            index[code] = record
    return index


def _batches(values, size=1000):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _master_cache(rows, customer):
    seasons = {f"{row['planning_year']}{row['planning_season_code']}".upper()
               for row in rows if row["planning_year"] and row["planning_season_code"]}
    products = {row["sample_code"].upper() for row in rows}
    product_index = {}
    for batch in _batches(sorted(products)):
        product_records = frappe.get_all("Product", filters={"product_code": ["in", batch]},
                                         fields=["name", "product_code", "customer"], limit_page_length=0)
        for record in product_records:
            code = record.product_code.upper()
            if record.customer not in (None, "", customer):
                continue
            if code in product_index:
                raise WorkbookError("SPL_MASTER_AMBIGUOUS", doctype="Product", code=code)
            product_index[code] = record
    indexes = {
        "Production Season": _lookup("Production Season", "season_code", seasons),
        "Market": _lookup("Market", "code", {r["market_code"].upper() for r in rows}),
        "Product": product_index,
        "Product Color": _lookup("Product Color", "color_code", {r["color_code"].upper() for r in rows}),
        "ProductSize": _lookup("ProductSize", "size_code", {r["size_code"].upper() for r in rows}),
    }
    product_names = [record.name for record in product_index.values()]
    variants = {}
    for batch in _batches(product_names):
        for record in frappe.get_all("Product Variant", filters={"product": ["in", batch]},
                                     fields=["name", "product", "market", "product_color", "size"],
                                     limit_page_length=0):
            key = (record.product, record.market or "", record.product_color, record.size)
            if key in variants:
                raise WorkbookError("SPL_MASTER_AMBIGUOUS", doctype="Product Variant", code=str(key))
            variants[key] = record.name
    indexes["Product Variant"] = variants
    return indexes


def _resolve(cache, staged, doctype, code, values):
    code = code.upper()
    if code in staged[doctype]:
        return staged[doctype][code]
    if code in cache[doctype]:
        return cache[doctype][code].name
    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.insert(ignore_permissions=True)
    staged[doctype][code] = doc.name
    return doc.name


def _import_group(settings, rows, cache, source_path):
    staged = defaultdict(dict)
    first = rows[0]
    season_code = (f"{first['planning_year']}{first['planning_season_code']}"
                   if first["planning_year"] and first["planning_season_code"] else "")
    season = (_resolve(cache, staged, "Production Season", season_code,
                       {"season_code": season_code, "season_name": season_code, "is_active": 1})
              if season_code else None)
    market_code = first["market_code"]
    market = _resolve(cache, staged, "Market", market_code,
                      {"code": market_code, "name_en": first["business_unit"] or market_code, "is_active": 1})
    source_key = hashlib.sha256(
        json.dumps([settings.customer, first["po_number"], first["revision_no"]],
                   ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    existing = frappe.db.get_value("SPL Purchase Order", {"source_key": source_key}, "name")
    po = frappe.get_doc("SPL Purchase Order", existing) if existing else frappe.new_doc("SPL Purchase Order")
    po.update({
        "source_key": source_key, "customer": settings.customer, "po_number": first["po_number"],
        "revision_no": first["revision_no"], "production_season": season, "market": market,
        "order_date": first["approval_date"] or first["revised_date"],
        "delivery_date": first["eta_wh"], "ship_date": first["contracted_etd"],
        "total_quantity": sum(r["order_qty"] for r in rows),
        "imported_at": now_datetime(), "last_source_file_path": source_path,
        "status": "Confirmed" if not existing else po.status,
    })
    for key in (
        "planning_year", "planning_season_code", "global_business_unit", "business_unit",
        "item_brand", "department", "revised_date", "document_status_external", "approver",
        "approval_date", "deadline_date", "answered_status_external", "decision_date",
        "sales_contract_no", "bill_to_name", "bill_to_address", "bill_to_telephone",
        "bill_to_person_in_charge", "incoterms", "transportation_method", "payment_terms",
        "payment_currency", "order_conditions", "order_plan_number", "contracted_etd", "eta_wh",
    ):
        po.set(key, first.get(key))
    po.set("items", [])
    for row in rows:
        product = _resolve(cache, staged, "Product", row["sample_code"], {
            "product_code": row["sample_code"], "product_name": row["item_name"],
            "customer": settings.customer, "production_season": season, "is_active": 0,
        })
        color = _resolve(cache, staged, "Product Color", row["color_code"], {
            "color_code": row["color_code"], "color_name": row["color_name"], "is_active": 1,
        })
        size = _resolve(cache, staged, "ProductSize", row["size_code"], {
            "size_code": row["size_code"], "size_label": row["size_name"], "is_active": 1,
        })
        row_market = _resolve(cache, staged, "Market", row["market_code"], {
            "code": row["market_code"], "name_en": row["business_unit"] or row["market_code"], "is_active": 1,
        })
        variant_key = (product, row_market, color, size)
        variant = staged["Product Variant"].get(variant_key) or cache["Product Variant"].get(variant_key)
        if not variant:
            variant = frappe.get_doc({"doctype": "Product Variant", "product": product,
                                      "market": row_market, "product_color": color, "size": size,
                                      "is_active": 1}).insert(ignore_permissions=True).name
            staged["Product Variant"][variant_key] = variant
        po.append("items", {
            "product": product, "product_variant": variant, "market": row_market,
            "product_color": color, "size": size, "order_qty": row["order_qty"],
            "unit_price": parse_unit_price(row["original_sales_price_text"]),
            "currency": normalize_currency(first["payment_currency"]),
            "import_line_key": f"{first['po_number']}|{first['revision_no']}|{row['row_number']}|{row['item_code']}",
            "item_code": row["item_code"], "item_name": row["item_name"],
            "pattern_dimension_code": row["pattern_dimension_code"], "sku": row["sku"],
            "sku_code_for_shipping": row["sku_code_for_shipping"], "sample_code": row["sample_code"],
            "representative_sample_code": row["representative_sample_code"],
            "allocation_order_number": row["allocation_order_number"],
            "original_sales_price_text": row["original_sales_price_text"],
            "external_remark": row["external_remark"], "source_row_number": row["row_number"],
        })
    if existing:
        po.save(ignore_permissions=True)
    else:
        po.insert(ignore_permissions=True)
    for doctype, entries in staged.items():
        for code, name in entries.items():
            cache[doctype][code] = frappe._dict(name=name) if doctype != "Product Variant" else name
    return len(rows)


def execute_import(run_name, token=None, selected_rows=None, scheduled=False):
    run = frappe.get_doc("SPL Import Run", run_name)
    lock = frappe.cache().lock(frappe.cache().make_key("spl-po-import"), timeout=3600,
                               blocking_timeout=0)
    if not lock.acquire(blocking=False):
        run.status = "Failed"
        run.message = message("SPL_ALREADY_RUNNING")
        run.completed_at = now_datetime()
        run.save(ignore_permissions=True)
        frappe.db.commit()
        return
    try:
        run.status = "Running"
        run.save(ignore_permissions=True)
        frappe.db.commit()
        settings = _settings()
        if scheduled:
            content, source_path = fetch_report(settings)
            rows = parse_workbook(content, source_path)
            if not rows:
                raise WorkbookError("SPL_NO_ROWS")
        else:
            data = _load_snapshot(run, token)
            if data["customer"] != settings.customer:
                raise WorkbookError("SPL_PREVIEW_INVALID")
            selected = set(selected_rows or [])
            rows = [row for row in data["rows"] if row["row_number"] in selected]
            source_path = run.source_file_path
        run.total_rows = len(rows)
        run.total_orders = len(_group(rows))
        errors = _validate(rows)
        cache = _master_cache(rows, settings.customer)
        failures = []
        for index, (key, group) in enumerate(_group(rows).items()):
            savepoint = f"spl_po_{index}"
            frappe.db.savepoint(savepoint)
            try:
                group_errors = [errors[row["row_number"]] for row in group if row["row_number"] in errors]
                if group_errors:
                    raise WorkbookError("SPL_GROUP_INVALID", po=key[0], revision=key[1])
                count = _import_group(settings, group, cache, source_path)
                run.imported_orders = (run.imported_orders or 0) + 1
                run.imported_items = (run.imported_items or 0) + count
                run.save(ignore_permissions=True)
                frappe.db.commit()
            except Exception as exc:
                frappe.db.rollback(save_point=savepoint)
                run.failed_orders = (run.failed_orders or 0) + 1
                failures.append(f"{key[0]} / {key[1]}: {_error(exc)}")
                # Failed group may have created masters before rollback; reload cache.
                cache = _master_cache(rows, settings.customer)
        run.status = ("Partial Success" if run.imported_orders else "Failed") if failures else "Success"
        run.error_detail = "\n".join(failures[:100])
        run.message = message("SPL_IMPORT_COMPLETE") if not failures else message("SPL_IMPORT_PARTIAL")
    except (WorkbookError, GatewayError) as exc:
        run.status = "Failed"
        run.message = _error(exc)
    except Exception:
        run.status = "Failed"
        run.message = message("SPL_IMPORT_FAILED")
    finally:
        run.completed_at = now_datetime()
        run.save(ignore_permissions=True)
        frappe.db.commit()
        lock.release()


def cleanup_snapshots():
    """Expire unconfirmed previews and prune private snapshots after job grace."""
    if not frappe.db.exists("DocType", "SPL Import Run"):
        return
    cutoff = now_datetime() - timedelta(hours=3)
    folder = Path(frappe.get_site_path("private", "files", "spl_po")).resolve()
    runs = frappe.get_all("SPL Import Run", filters={
        "snapshot_expires_at": ["<", cutoff], "snapshot_path": ["is", "set"],
    }, fields=["name", "status", "snapshot_path", "snapshot_token"], limit_page_length=500)
    for row in runs:
        path = Path(row.snapshot_path).resolve()
        if path.parent == folder and path.name == f"{row.snapshot_token}.json.gz":
            path.unlink(missing_ok=True)
        if row.status == "Preview Ready":
            frappe.db.set_value("SPL Import Run", row.name, "status", "Expired", update_modified=False)
        frappe.db.set_value("SPL Import Run", row.name, "snapshot_path", "", update_modified=False)
