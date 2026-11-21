"""Private preview and transactional import of Trim orders."""

import gzip
import json
import os
import secrets
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import frappe
from frappe.utils import get_datetime, now_datetime

from factory_management.trim.parser import MAX_BYTES, WorkbookError, parse_workbook
from factory_management.trim.identity import source_key

IMPORT_BATCH_SIZE = 50


def _groups(rows):
    groups = defaultdict(list)
    for row in rows:
        header = row["header"]
        groups[(header["order_no"], header["revision_no"])].append(row)
    return groups


def _new_run():
    run = frappe.get_doc({"doctype": "Trim Import Run", "status": "Queued",
                          "requested_by": frappe.session.user, "started_at": now_datetime()})
    run.insert(ignore_permissions=True)
    return run


def _folder():
    path = Path(frappe.get_site_path("private", "files", "trim_import")).resolve()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def _upload(file_url):
    name = frappe.db.get_value("File", {"file_url": file_url, "is_private": 1}, "name")
    if not name:
        raise WorkbookError("Upload must be a private File")
    doc = frappe.get_doc("File", name)
    path = Path(doc.get_full_path()).resolve()
    root = Path(frappe.get_site_path("private")).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise WorkbookError("Uploaded file is invalid or too large")
    return path.read_bytes(), doc.file_name


def _save_snapshot(rows):
    token = secrets.token_urlsafe(32)
    path = _folder() / f"{token}.json.gz"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb") as stream:
            stream.write(json.dumps(rows, ensure_ascii=False).encode("utf-8"))
    return token, str(path)


def _load_snapshot(run, token):
    if not token or not secrets.compare_digest(token, run.snapshot_token or ""):
        raise WorkbookError("Preview token is invalid")
    if not run.snapshot_expires_at or get_datetime(run.snapshot_expires_at) < now_datetime():
        raise WorkbookError("Preview has expired; upload the workbook again")
    path = (_folder() / f"{token}.json.gz").resolve()
    if Path(run.snapshot_path or "").resolve() != path or not path.is_file():
        raise WorkbookError("Preview snapshot is missing")
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def queue_preview(file_url):
    run = _new_run()
    frappe.enqueue("factory_management.trim.service.prepare_preview", queue="long",
                   timeout=3600, enqueue_after_commit=True, job_name=f"trim-preview-{run.name}",
                   run_name=run.name, file_url=file_url)
    return run.name


def prepare_preview(run_name, file_url):
    run = frappe.get_doc("Trim Import Run", run_name)
    run.status = "Running"
    run.save(ignore_permissions=True)
    frappe.db.commit()
    try:
        content, filename = _upload(file_url)
        rows = parse_workbook(content, filename)
        groups = _groups(rows)
        # Header values are repeated on every detail row in the source report.
        for key, group in groups.items():
            first = group[0]["header"]
            if any(row["header"] != first for row in group[1:]):
                raise WorkbookError(f"Conflicting order header: {key[0]} / {key[1]}")
        token, path = _save_snapshot(rows)
        run.snapshot_token = token
        run.snapshot_path = path
        run.snapshot_expires_at = now_datetime() + timedelta(minutes=15)
        run.source_file = filename
        run.total_rows = len(rows)
        run.total_orders = len(groups)
        run.status = "Preview Ready"
        run.message = "Review the preview, then confirm Import."
    except WorkbookError as exc:
        run.status = "Failed"
        run.message = str(exc)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Trim preview failed")
        run.status = "Failed"
        run.message = "Could not preview the workbook."
    run.completed_at = now_datetime()
    run.save(ignore_permissions=True)
    frappe.db.commit()


def preview_page(run, token, page=1):
    if run.status != "Preview Ready":
        raise WorkbookError("Preview is not ready")
    rows = _load_snapshot(run, token)
    page = max(1, int(page))
    size = 100
    shown = rows[(page - 1) * size:page * size]
    statuses = defaultdict(int)
    for row in rows:
        statuses[row["header"]["document_status"]] += 1
    return {
        "rows": [{"row_number": row["row_number"], "order_no": row["header"]["order_no"],
                  "revision_no": row["header"]["revision_no"],
                  "document_status": row["header"]["document_status"],
                  "raw_material_code": row["item"]["raw_material_code"],
                  "supplier_raw_material_code": row["item"]["supplier_raw_material_code"],
                  "item_code": row["item"]["item_code"], "color": row["item"]["color"],
                  "size": row["item"]["size"], "order_qty": row["item"]["order_qty"]}
                 for row in shown],
        "total_rows": len(rows), "total_orders": len(_groups(rows)),
        "status_counts": dict(statuses), "page": page, "page_size": size,
        "expires_at": run.snapshot_expires_at,
    }


def queue_import(source, token):
    if source.status != "Preview Ready":
        raise WorkbookError("Preview is not ready")
    rows = _load_snapshot(source, token)
    run = _new_run()
    run.snapshot_token = token
    run.snapshot_path = source.snapshot_path
    run.snapshot_expires_at = now_datetime() + timedelta(hours=2)
    run.source_file = source.source_file
    run.total_rows = len(rows)
    run.total_orders = len(_groups(rows))
    run.save(ignore_permissions=True)
    source.status = "Expired"
    source.save(ignore_permissions=True)
    frappe.enqueue("factory_management.trim.service.execute_import", queue="long",
                   timeout=3600, enqueue_after_commit=True, job_name=f"trim-import-{run.name}",
                   run_name=run.name, token=token)
    return run.name


def _import_group(group):
    header = group[0]["header"]
    key = source_key(header["order_no"], header["revision_no"])
    existing = frappe.db.get_value("Trim", {"source_key": key}, "name")
    doc = frappe.get_doc("Trim", existing) if existing else frappe.new_doc("Trim")
    doc.update({**header, "source_key": key,
                "total_quantity": sum(row["item"]["order_qty"] for row in group),
                "imported_at": now_datetime()})
    doc.set("items", [])
    for row in group:
        doc.append("items", {**row["item"], "source_row_number": row["row_number"]})
    if existing:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)
    return len(group)


def execute_import(run_name, token):
    run = frappe.get_doc("Trim Import Run", run_name)
    lock = frappe.cache().lock(frappe.cache().make_key("trim-import"), timeout=3600,
                               blocking_timeout=0)
    if not lock.acquire(blocking=False):
        run.status = "Failed"
        run.message = "Another Trim import is running."
        run.completed_at = now_datetime()
        run.save(ignore_permissions=True)
        frappe.db.commit()
        return
    try:
        run.status = "Running"
        run.save(ignore_permissions=True)
        frappe.db.commit()
        rows = _load_snapshot(run, token)
        failures = []
        groups = _groups(rows)
        for index, (key, group) in enumerate(groups.items()):
            savepoint = f"trim_{index}"
            frappe.db.savepoint(savepoint)
            try:
                count = _import_group(group)
                run.imported_orders = (run.imported_orders or 0) + 1
                run.imported_items = (run.imported_items or 0) + count
            except Exception:
                frappe.db.rollback(save_point=savepoint)
                run.failed_orders = (run.failed_orders or 0) + 1
                failures.append(f"{key[0]} / {key[1]}")
                frappe.log_error(frappe.get_traceback(), "Trim order import failed")
            if (index + 1) % IMPORT_BATCH_SIZE == 0:
                run.save(ignore_permissions=True)
                frappe.db.commit()
        run.status = ("Partial Success" if run.imported_orders else "Failed") if failures else "Success"
        run.error_detail = "Failed orders: " + ", ".join(failures[:100]) if failures else ""
        run.message = "Import finished."
    except WorkbookError as exc:
        frappe.db.rollback()
        run.reload()
        run.status = "Failed"
        run.message = str(exc)
    except Exception:
        frappe.db.rollback()
        run.reload()
        frappe.log_error(frappe.get_traceback(), "Trim import failed")
        run.status = "Failed"
        run.message = "Import failed. Check the server error log."
    finally:
        run.completed_at = now_datetime()
        run.save(ignore_permissions=True)
        frappe.db.commit()
        lock.release()


def cleanup_snapshots():
    if not frappe.db.exists("DocType", "Trim Import Run"):
        return
    cutoff = now_datetime() - timedelta(hours=3)
    folder = _folder()
    for row in frappe.get_all("Trim Import Run", filters={"snapshot_expires_at": ["<", cutoff]},
                              fields=["name", "snapshot_path"], limit_page_length=1000):
        path = Path(row.snapshot_path or "").resolve()
        if path.parent == folder and path.suffix == ".gz":
            path.unlink(missing_ok=True)
        frappe.db.set_value("Trim Import Run", row.name, "snapshot_path", "", update_modified=False)
