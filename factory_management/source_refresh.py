"""Local Bench entry points for a verified one-time SQL Server QC refresh.

This module is intentionally not whitelisted. MigrationFrappe calls it inside the
selected Docker backend after creating a full site backup.
"""

import hashlib
import json
import uuid
from pathlib import Path

import frappe

from factory_management import __version__, data_epoch, importer
from factory_management.patches.separate_uqqc_defects import CATALOGS, _copy_missing


TABLES = (
    "Companies", "Factories", "Customers", "ProductionSeasons", "Products",
    "Colors", "Sizes", "Markets", "ProductVariants", "ProductionLines",
    "LineGroups", "LineGroupDetails", "QCDefectGroups", "QCDefects",
    "QCDefectPositionGroups", "QCDefectPositions", "Devices", "QCInspections",
)
MANAGED = (
    "QC Inspection Event", "UQQC Inspection Event", "QC Favorite", "QC Legacy Map",
    "Factory Device",
    "Product Variant", "Line Group Assignment", "QC Defect", "QC Defect Position",
    "UQQC Defect", "UQQC Defect Position", "Production Line", "Line Group",
    "Product", "Production Season", "Customer", "Product Color", "Color", "ProductSize", "Market",
    "Factory", "Company",
)
DELETE_ORDER = MANAGED
REFERENCE_FIELDS = {
    "Factories": {"CompanyId": "Companies"},
    "Products": {"CustomerId": "Customers", "SeasonId": "ProductionSeasons"},
    "ProductVariants": {"ProductId": "Products", "ColorId": "Colors", "SizeId": "Sizes", "MarketId": "Markets"},
    "ProductionLines": {"CompanyId": "Companies", "FactoryId": "Factories"},
    "LineGroups": {"CompanyId": "Companies", "FactoryId": "Factories"},
    "LineGroupDetails": {"LineId": "ProductionLines", "LineGroupId": "LineGroups"},
    "QCDefects": {"DefectGroupId": "QCDefectGroups"},
    "QCDefectPositions": {"PositionGroupId": "QCDefectPositionGroups"},
    "Devices": {"CompanyId": "Companies", "FactoryId": "Factories", "LineId": "ProductionLines"},
    "QCInspections": {"DeviceActivationId": "Devices", "ProductId": "Products",
                      "LineId": "ProductionLines", "DefectId": "QCDefects",
                      "ColorId": "Colors", "SizeId": "Sizes"},
}


class RefreshError(ValueError):
    def __init__(self, code, detail=""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def _rows(directory, table):
    path = directory / (table + ".jsonl")
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise RefreshError("InvalidSnapshot", table)
                yield row


def _snapshot(directory):
    root = Path(directory).resolve(strict=True)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("formatVersion") != 1 or set(manifest.get("tables", {})) != set(TABLES):
        raise RefreshError("InvalidSnapshot")
    for table in TABLES:
        item = manifest["tables"][table]
        path = root / (table + ".jsonl")
        if path.is_symlink() or not path.is_file():
            raise RefreshError("InvalidSnapshot", table)
        digest = hashlib.sha256()
        count = 0
        with path.open("rb") as stream:
            for line in stream:
                digest.update(line)
                count += 1
        if count != item.get("count") or digest.hexdigest() != item.get("sha256"):
            raise RefreshError("ChecksumMismatch", table)
    summary = "\n".join(f"{table}:{manifest['tables'][table]['count']}:{manifest['tables'][table]['sha256']}"
                        for table in sorted(TABLES))
    if hashlib.sha256(summary.encode("utf-8")).hexdigest() != manifest.get("snapshotSha256"):
        raise RefreshError("ChecksumMismatch", "manifest")
    return root, manifest


def _check_relations(directory):
    ids = {}
    codes = {}
    uids = set()
    variants = set()
    event_keys = set()
    size_labels = set()
    for table in TABLES:
        seen, seen_codes = set(), set()
        for row in _rows(directory, table):
            source_id = str(row.get("Id") or "").lower()
            if not source_id or source_id in seen:
                raise RefreshError("DuplicateSourceId", table)
            seen.add(source_id)
            if table not in ("ProductVariants", "LineGroupDetails", "Devices", "QCInspections"):
                code = str(row.get("Code") or "").strip().casefold()
                if not code:
                    raise RefreshError("DuplicateSourceCode", table + ":" + code)
                # Factory codes are unique within a Company; other code-named
                # masters remain globally unique within their destination DocType.
                if table == "Factories":
                    company_id = str(row.get("CompanyId") or "").strip().casefold()
                    if not company_id:
                        raise RefreshError("MissingReference", "Factories.CompanyId")
                    identity = (company_id, code)
                    if identity in seen_codes:
                        raise RefreshError("DuplicateSourceCode", table + ":" + code)
                    seen_codes.add(identity)
                elif table in ("Companies", "Colors", "ProductionSeasons", "LineGroups"):
                    if code in seen_codes:
                        raise RefreshError("DuplicateSourceCode", table + ":" + code)
                    seen_codes.add(code)
            if table == "Devices":
                try:
                    uuid.UUID(source_id)
                except ValueError:
                    raise RefreshError("InvalidSnapshot", "Devices.Id") from None
                uid = str(row.get("DeviceUid") or "").strip().casefold()
                if uid and uid in uids:
                    raise RefreshError("DuplicateDeviceUid", uid)
                if uid:
                    uids.add(uid)
            if table == "ProductVariants":
                variant = tuple(str(row.get(field) or "").lower() for field in
                                ("ProductId", "ColorId", "SizeId", "MarketId"))
                if variant in variants:
                    raise RefreshError("DuplicateSourceId", table)
                variants.add(variant)
            if table == "Sizes":
                label = str(row.get("Name") or "").strip()
                normalized_label = label.casefold()
                if not label or len(label) > 140:
                    raise RefreshError("InvalidSnapshot", "Sizes.SizeLabel")
                if normalized_label in size_labels:
                    raise RefreshError("DuplicateSourceCode", "Sizes.SizeLabel:" + label)
                size_labels.add(normalized_label)
            if table == "QCInspections" and (row.get("IsDeleted") or row.get("Source") != "QC"):
                raise RefreshError("InvalidSnapshot", table)
            if table == "QCInspections":
                local_id = str(row.get("LocalEventId") or "sql:" + str(row.get("Id"))).strip()
                key = (str(row.get("DeviceUid") or "").strip().casefold(), local_id.casefold())
                if not key[0] or len(local_id) > 100 or key in event_keys:
                    raise RefreshError("DuplicateEventUid", table + ":" + local_id)
                if not str(row.get("EventType") or "").strip() or not row.get("OccurredAt"):
                    raise RefreshError("InvalidSnapshot", table + ":" + str(row.get("Id")))
                event_keys.add(key)
        ids[table], codes[table] = seen, seen_codes

    # Defect groups and defects share one destination DocType, so their codes
    # must be unique across both source tables when QC Defect names use Code.
    defect_codes = {}
    for table in ("QCDefectGroups", "QCDefects"):
        for row in _rows(directory, table):
            code = str(row.get("Code") or "").strip().casefold()
            previous = defect_codes.get(code)
            if previous:
                raise RefreshError("DuplicateSourceCode", f"{previous}/{table}:{code}")
            defect_codes[code] = table

    for table, fields in REFERENCE_FIELDS.items():
        for row in _rows(directory, table):
            for field, target in fields.items():
                reference = str(row.get(field) or "").lower()
                if reference and reference not in ids[target]:
                    raise RefreshError("MissingReference", f"{table}.{field}:{reference}")
            if table == "QCInspections":
                device_uid = str(row.get("DeviceUid") or "").strip().casefold()
                if not row.get("DeviceActivationId") and device_uid not in uids:
                    raise RefreshError("MissingReference", f"QCInspections.DeviceUid:{device_uid}")


def _external_references():
    managed = set(MANAGED)
    conflicts = []
    # Frappe framework metadata and the app's own records are handled separately.
    for field_type in ("DocField", "Custom Field"):
        owner_field = "parent" if field_type == "DocField" else "dt"
        for field in frappe.get_all(field_type, filters={"fieldtype": "Link"},
                                    fields=[owner_field + " as parent", "fieldname", "options"],
                                    limit_page_length=0):
            if field.options not in managed or field.parent in managed:
                continue
            if not frappe.db.exists("DocType", field.parent) or not frappe.db.table_exists(field.parent):
                continue
            try:
                count = frappe.db.count(field.parent, {field.fieldname: ["!=", ""]})
            except Exception:
                raise RefreshError("ExternalReferenceUnknown", f"{field.parent}.{field.fieldname}")
            if count:
                conflicts.append({"doctype": field.parent, "field": field.fieldname,
                                  "target": field.options, "count": count})
    # Dynamic Links cannot be checked by a fixed target DocType field. Block on
    # nonempty dynamic references outside our allowlist rather than lose links.
    for field_type in ("DocField", "Custom Field"):
        owner_field = "parent" if field_type == "DocField" else "dt"
        for field in frappe.get_all(field_type, filters={"fieldtype": "Dynamic Link"},
                                    fields=[owner_field + " as parent", "fieldname", "options"],
                                    limit_page_length=0):
            if field.parent in managed or not frappe.db.exists("DocType", field.parent):
                continue
            if not frappe.db.table_exists(field.parent):
                continue
            # Framework audit data is not a business Link and survives the refresh.
            if field.parent in {"Communication", "Comment", "Version", "Activity Log", "File"}:
                continue
            if field.options and frappe.db.count(field.parent, {field.options: ["in", list(managed)]}):
                conflicts.append({"doctype": field.parent, "field": field.fieldname,
                                  "target": field.options, "count": 1})
    return conflicts


def preflight(directory):
    root, manifest = _snapshot(directory)
    try:
        app_version = tuple(int(part) for part in __version__.split(".")[:3])
    except (AttributeError, TypeError, ValueError):
        app_version = ()
    if app_version < (0, 1, 21) or not frappe.db.exists("DocType", "Factory Data Epoch"):
        raise RefreshError("RefreshAppUpgradeRequired")
    _check_relations(root)
    conflicts = _external_references()
    counts = {doctype: frappe.db.count(doctype) for doctype in MANAGED}
    counts["File"] = frappe.db.count("File", {"attached_to_doctype": ["in", list(MANAGED)]})
    return {"site": frappe.local.site, "sourceCounts": {table: manifest["tables"][table]["count"]
            for table in TABLES}, "existingCounts": counts, "conflicts": conflicts,
            "snapshotSha256": manifest.get("snapshotSha256", "")}


def _import_master(table, row):
    current = dict(row)
    retired = bool(current.get("IsDeleted"))
    current["IsDeleted"] = False
    current["IsActive"] = bool(current.get("IsActive", True)) and not retired
    if table == "Devices":
        current["IsActive"] = current["IsActive"] and current.get("Status") != "Deactivated"
    if table == "LineGroupDetails":
        name = importer._new("Line Group Assignment", {
            "assignment_uid": importer._uid(table, str(row["Id"])),
            "legacy_id": str(row["Id"]),
            "line": importer._target("ProductionLines", row.get("LineId")),
            "line_group": importer._target("LineGroups", row.get("LineGroupId")),
            "is_active": int(current["IsActive"]),
        })
        importer._save_map(table, str(row["Id"]), "Line Group Assignment", name)
    else:
        importer._import_one(table, current)


def _import_event(row, uid_to_id):
    from factory_management import api as qc_api
    device = importer._target("Devices", row.get("DeviceActivationId"))
    if not device:
        device = importer._target("Devices", uid_to_id.get(str(row.get("DeviceUid") or "").strip().casefold()))
    if not device:
        raise RefreshError("MissingReference", "QCInspections.DeviceUid")
    local_id = str(row.get("LocalEventId") or "sql:" + str(row["Id"]))
    if len(local_id) > 100:
        raise RefreshError("InvalidEventId", str(row["Id"]))
    uid = hashlib.sha256((device + "|" + local_id.casefold()).encode("utf-8")).hexdigest()
    if frappe.db.exists("QC Inspection Event", {"event_uid": uid}):
        raise RefreshError("DuplicateEventUid", uid)
    occurred = qc_api._as_utc(row.get("OccurredAt"))
    frappe.get_doc({
        "doctype": "QC Inspection Event", "event_uid": uid, "local_event_id": local_id,
        "device": device, "event_type": row.get("EventType") or "",
        "product": importer._target("Products", row.get("ProductId")),
        "line": importer._target("ProductionLines", row.get("LineId")),
        "color": importer._target("Colors", row.get("ColorId")),
        "size": importer._target("Sizes", row.get("SizeId")),
        "defect": importer._target("QCDefects", row.get("DefectId")),
        "quantity_delta": row.get("QuantityDelta") or 0,
        "occurred_at": occurred.strftime("%Y-%m-%d %H:%M:%S.%f"),
        "synced_at": qc_api._as_db_utc(row["SyncedAt"]) if row.get("SyncedAt") else None,
        "server_date_key": occurred.astimezone(qc_api._time_zone()).date().isoformat(),
    }).insert(ignore_permissions=True)


def _verify_identity_maps(directory, uid_to_id):
    checksums = {}
    mapped_devices = {}
    for table in TABLES[:-1]:
        expected = {str(row["Id"]).casefold() for row in _rows(directory, table)}
        maps = frappe.get_all("QC Legacy Map", filters={"source_table": table},
                              fields=["legacy_id", "target_doctype", "target_name"],
                              limit_page_length=0)
        actual = {str(row.legacy_id).casefold(): row for row in maps}
        if len(actual) != len(maps) or set(actual) != expected:
            raise RefreshError("CountMismatch", table + ":legacy-map")
        target_doctype = importer.SOURCES[table][0]
        for legacy_id, mapping in actual.items():
            if mapping.target_doctype != target_doctype or not frappe.db.exists(
                    mapping.target_doctype, mapping.target_name):
                raise RefreshError("CountMismatch", table + ":target:" + legacy_id)
        digest = hashlib.sha256("\n".join(sorted(actual)).encode("utf-8")).hexdigest()
        checksums[table] = digest
        if table == "Devices":
            mapped_devices = {legacy_id: mapping.target_name for legacy_id, mapping in actual.items()}

    expected_events = set()
    for row in _rows(directory, "QCInspections"):
        device = mapped_devices.get(str(row.get("DeviceActivationId") or "").casefold())
        if not device:
            device = mapped_devices.get(uid_to_id.get(str(row.get("DeviceUid") or "").strip().casefold()))
        if not device:
            raise RefreshError("MissingReference", "QCInspections.DeviceUid")
        local_id = str(row.get("LocalEventId") or "sql:" + str(row["Id"]))
        expected_events.add(hashlib.sha256((device + "|" + local_id.casefold()).encode("utf-8")).hexdigest())
    actual_events = set(frappe.get_all("QC Inspection Event", pluck="event_uid", limit_page_length=0))
    if actual_events != expected_events:
        raise RefreshError("CountMismatch", "QCInspections:event-uid")
    checksums["QCInspections"] = hashlib.sha256(
        "\n".join(sorted(actual_events)).encode("utf-8")).hexdigest()
    return checksums


def apply(directory):
    data_epoch.lock()
    preview = preflight(directory)
    if preview["conflicts"]:
        raise RefreshError("ExternalReferenceConflict", json.dumps(preview["conflicts"], ensure_ascii=False))
    if not frappe.conf.maintenance_mode:
        raise RefreshError("MaintenanceRequired")
    root = Path(directory)
    uid_to_id = {str(row.get("DeviceUid") or "").strip().casefold(): str(row["Id"]).casefold()
                 for row in _rows(root, "Devices") if row.get("DeviceUid")}
    try:
        files = frappe.get_all("File", filters={"attached_to_doctype": ["in", list(MANAGED)]},
                               pluck="name", limit_page_length=0)
        for name in files:
            frappe.delete_doc("File", name, ignore_permissions=True)
        for doctype in DELETE_ORDER:
            frappe.db.delete(doctype)
        for table in TABLES[:-1]:
            for row in _rows(root, table):
                _import_master(table, row)
        for row in _rows(root, "QCInspections"):
            _import_event(row, uid_to_id)
        source_rows = {source: frappe.get_all(source, fields=["name", *fields],
                                              limit_page_length=0)
                       for source, _, fields in CATALOGS}
        _copy_missing(source_rows)
        for source, target, _ in CATALOGS:
            if {row.name for row in source_rows[source]} != set(
                    frappe.get_all(target, pluck="name", limit_page_length=0)):
                raise RefreshError("CountMismatch", target)
        verification_checksums = _verify_identity_maps(root, uid_to_id)
        for table, count in preview["sourceCounts"].items():
            if table == "QCInspections":
                actual = frappe.db.count("QC Inspection Event")
            elif table == "QCDefectGroups":
                actual = frappe.db.count("QC Defect", {"record_type": "Group"})
            elif table == "QCDefects":
                actual = frappe.db.count("QC Defect", {"record_type": "Defect"})
            elif table == "QCDefectPositionGroups":
                actual = frappe.db.count("QC Defect Position", {"record_type": "Group"})
            elif table == "QCDefectPositions":
                actual = frappe.db.count("QC Defect Position", {"record_type": "Position"})
            else:
                actual = frappe.db.count(importer.SOURCES[table][0])
            if actual != count:
                raise RefreshError("CountMismatch", f"{table}:{actual}/{count}")
        if frappe.db.count("UQQC Inspection Event"):
            raise RefreshError("CountMismatch", "UQQC")
        generation = data_epoch.rotate()
        frappe.db.commit()
        frappe.clear_cache()
        return {"site": frappe.local.site, "counts": preview["sourceCounts"],
                "generation": generation,
                "verificationSha256": hashlib.sha256("\n".join(
                    f"{table}:{verification_checksums[table]}" for table in sorted(verification_checksums)
                ).encode("utf-8")).hexdigest()}
    except BaseException:
        frappe.db.rollback()
        raise
