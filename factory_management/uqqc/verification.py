"""Explicit integration verification with temporary data, always rolled back.

Run: bench --site <site> execute factory_management.uqqc.verification.run
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from factory_management import device_registry
from factory_management import api as qc_api
from factory_management import data_epoch
from factory_management.uqqc import api
from factory_management.uqqc.access import OPERATIONS, READER_ROLE
from factory_management.uqqc.provision import CATALOG_MANAGER_ROLE


def browser_fixture():
    """Create a dedicated browser test device; never attach to a production device."""
    device_id = str(uuid.uuid4())
    secret = uuid.uuid4().hex + uuid.uuid4().hex
    line = frappe.db.get_value("Production Line", {"is_active": 1, "company": ["is", "set"]}, ["name", "company"], as_dict=True)
    assert line
    frappe.get_doc({
        "doctype": device_registry.DEVICE_TYPE, "device_id": device_id, "device_uid": "uqqc-browser-" + device_id,
        "device_name": "UQQC browser verification", "status": "Approved", "is_active": 1,
        "company": line.company, "line": line.name,
    }).insert(ignore_permissions=True)
    device_registry.register_client(frappe.get_doc(device_registry.DEVICE_TYPE, device_id), "uqqc", secret)
    return {"device_id": device_id, "token": secret}


def remove_browser_fixture(device_id: str):
    device = frappe.get_doc(device_registry.DEVICE_TYPE, device_id)
    assert device.device_uid == "uqqc-browser-" + device_id
    frappe.db.delete(api.EVENT_TYPE, {"device": device_id})
    frappe.db.delete(device_registry.CLIENT_TYPE, {"device": device_id})
    frappe.delete_doc(device_registry.DEVICE_TYPE, device_id, ignore_permissions=True)


def run():
    old_user = frappe.session.user
    old_request = getattr(frappe.local, "request", None)
    old_form = getattr(frappe.local, "form_dict", None)
    old_response = getattr(frappe.local, "response", None)
    user = None
    catalog_manager = None
    passed = []
    frappe.db.savepoint("uqqc_verification")
    try:
        frappe.set_user("Administrator")
        line = frappe.db.get_value("Production Line", {"is_active": 1, "company": ["is", "set"]}, ["name", "company"], as_dict=True)
        variant = frappe.db.get_value("Product Variant", {"is_active": 1, "qc_color": ["is", "set"], "size": ["is", "set"], "market": ["is", "set"]}, ["product", "qc_color", "size", "market"], as_dict=True)
        defect = frappe.db.get_value("UQQC Defect", {"is_active": 1, "record_type": "Defect"}, "name")
        position = frappe.db.get_value("UQQC Defect Position", {"is_active": 1, "record_type": "Position"}, "name")
        assert line and variant and defect and position
        device_id = str(uuid.uuid4())
        qc_secret = uuid.uuid4().hex + uuid.uuid4().hex
        uqqc_secret = uuid.uuid4().hex + uuid.uuid4().hex
        frappe.get_doc({
            "doctype": device_registry.DEVICE_TYPE, "device_id": device_id, "device_uid": device_id,
            "device_name": "UQQC verification", "status": "Approved", "is_active": 1,
            "company": line.company, "line": line.name,
        }).insert(ignore_permissions=True)
        device_registry.register_client(frappe.get_doc(device_registry.DEVICE_TYPE, device_id), "qc", qc_secret)
        assert device_registry.client_pairing(frappe.get_doc(device_registry.DEVICE_TYPE, device_id), "qc", qc_secret)[0] == "Paired"
        qc_request = EnvironBuilder(path="/api/method/factory_management.api.bootstrap", method="GET",
                                    headers={"X-QC-Token": qc_secret})
        frappe.local.request = Request(qc_request.get_environ())
        assert "catalog" in qc_api.bootstrap(device_id)
        qc_request.close()
        scope = {"lineId": line.name, "productId": variant.product, "colorId": variant.qc_color,
                 "sizeId": variant.size, "marketId": variant.market}

        def invoke(operation, payload=None, auth=uqqc_secret, session="Guest", path=None, method=None,
                   generation=None):
            frappe.set_user(session)
            http_method, route, _ = OPERATIONS[operation]
            payload = {"deviceId": device_id, **(payload or {})}
            actual_method = method or http_method
            body = {"query_string": payload} if actual_method == "GET" else {"data": json.dumps(payload)}
            headers = {"X-UQQC-Token": auth} if auth else {}
            headers[data_epoch.HEADER] = generation if generation is not None else data_epoch.current()["generation"]
            builder = EnvironBuilder(path=path or "/api/method/" + route, method=actual_method,
                                     headers=headers,
                                     content_type="application/json", **body)
            frappe.local.request = Request(builder.get_environ())
            frappe.local.form_dict = frappe._dict(payload)
            frappe.local.response = frappe._dict(type="json")
            frappe.db.savepoint("uqqc_request")
            try:
                frappe.get_doc("Server Script", "UQQC " + operation.replace("_", " ").title()).execute_method()
                return frappe.response.message
            except Exception:
                frappe.db.rollback(save_point="uqqc_request")
                raise
            finally:
                builder.close()

        def denied(operation, payload=None, **kwargs):
            try:
                invoke(operation, payload, **kwargs)
            except (frappe.PermissionError, frappe.ValidationError):
                return
            raise AssertionError(operation)

        denied("bootstrap", auth=qc_secret)  # A QC-only credential cannot access UQQC.
        assert invoke("device_register", auth=uqqc_secret)["isActive"]
        assert invoke("device_check")["id"] == device_id
        denied("bootstrap", auth=qc_secret)
        catalog = invoke("bootstrap")
        assert any(item["id"] == line.name for item in catalog["lines"])
        assert all(item["companyId"] == line.company for item in catalog["lines"])
        selected = catalog["productVariants"][0]
        scope = {"lineId": line.name, **selected}
        defect = catalog["defects"][0]["id"]
        position = catalog["defectPositions"][0]["id"]
        passed.append("six_script_activation_and_bootstrap")
        for operation in OPERATIONS:
            denied(operation, auth="invalid")
        client_name = frappe.db.get_value(device_registry.CLIENT_TYPE,
                                          {"device": device_id, "service_key": "uqqc"}, "name")
        frappe.db.set_value(device_registry.CLIENT_TYPE, client_name, "status", "Revoked")
        denied("bootstrap")
        denied("device_register")
        denied("device_check")
        assert device_registry.client_pairing(
            frappe.get_doc(device_registry.DEVICE_TYPE, device_id), "qc", qc_secret,
        )[0] == "Paired"
        frappe.db.set_value(device_registry.CLIENT_TYPE, client_name, "status", "Approved")
        denied("bootstrap", path="/api/method/factory_management.uqqc.api.dispatch")
        denied("sync", method="GET")
        frappe.db.set_value(device_registry.DEVICE_TYPE, device_id, "is_active", 0)
        denied("bootstrap")
        frappe.db.set_value(device_registry.DEVICE_TYPE, device_id, "is_active", 1)
        frappe.db.set_value(device_registry.DEVICE_TYPE, device_id, "status", "Pending")
        denied("sync")
        frappe.db.set_value(device_registry.DEVICE_TYPE, device_id, "status", "Approved")
        passed.append("token_status_method_and_alias_guards")

        now = datetime.now(timezone.utc).isoformat()
        piece = str(uuid.uuid4())
        event = {**scope, "localEventId": "defect-1", "occurredAt": now, "schemaVersion": 2,
                 "quantityDelta": 1, "defectId": defect, "defectPositionId": position, "defectPieceId": piece}
        batch = {"events": [event, {**event, "localEventId": "defect-2"}],
                 "passEvents": [{**scope, "localEventId": "pass-1", "occurredAt": now},
                                {**scope, "localEventId": "pass-2", "occurredAt": now}],
                 "reworkEvents": [{**scope, "localEventId": "rework-1", "occurredAt": now}]}
        assert invoke("sync", batch)["acceptedCount"] == 5
        assert invoke("sync", batch)["acceptedCount"] == 5
        assert frappe.db.count(api.EVENT_TYPE, {"device": device_id}) == 5
        totals = invoke("snapshot", scope)
        assert (totals["pass"], totals["rework"], totals["total"], totals["defectNo"], totals["defectPcs"], totals["passRate"]) == (2, 1, 3, 2, 1, 66.7)
        assert totals["defectPieceIds"] == [piece]
        details = invoke("detail_snapshot")
        assert len(details["scopes"]) == 1 and details["scopes"][0]["defectNo"] == 2
        passed.append("idempotency_piece_metrics_and_detail")

        qc_event = {"local_event_id": "qc-verification-" + uuid.uuid4().hex,
                    "event_type": "CumulativeAdd", "product": variant.product, "line": line.name,
                    "color": variant.qc_color, "size": variant.size,
                    "quantity_delta": 1, "occurred_at": now}
        qc_builder = EnvironBuilder(path="/api/method/factory_management.api.sync_events", method="POST",
                                    headers={"X-QC-Token": qc_secret,
                                             data_epoch.HEADER: data_epoch.current()["generation"]})
        frappe.local.request = Request(qc_builder.get_environ())
        try:
            assert qc_api.sync_events(device_id, [qc_event])["accepted_count"] == 1
            assert qc_api.sync_events(device_id, [qc_event])["accepted_count"] == 0
            assert qc_api.snapshot(device_id, variant.product, line.name,
                                   variant.qc_color, variant.size)["received"] == 1
        finally:
            qc_builder.close()
        passed.append("qc_sync_replay_and_snapshot_without_retired_fields")

        denied("sync", {"events": [{**event, "quantityDelta": -1}]})
        denied("sync", batch, generation="previous-generation")
        denied("sync", {"events": [{**event, "defectPositionId": None}]})
        denied("sync", {"events": [{**event, "defectPieceId": str(uuid.UUID(int=0))}]})
        denied("sync", {"passEvents": [{**scope, "localEventId": "fresh", "occurredAt": now}, {**scope, "localEventId": "bad", "occurredAt": "invalid"}]})
        assert frappe.db.count(api.EVENT_TYPE, {"device": device_id}) == 5
        denied("sync", {"passEvents": [{**scope, "localEventId": "fresh", "occurredAt": now}, {**scope, "localEventId": "defect-1", "occurredAt": now}]})
        assert frappe.db.count(api.EVENT_TYPE, {"device": device_id}) == 5
        denied("sync", {"events": [event] * 501})
        denied("snapshot", {**scope, "marketId": "invalid"})
        # Explicitly exercise the company fence without modifying existing master rows.
        with patch("factory_management.uqqc.api._master_value", wraps=api._master_value) as get_value:
            real_get = get_value._mock_wraps
            get_value.side_effect = lambda doctype, *args, **kwargs: "another-company" if doctype == "Production Line" and len(args) > 1 and args[1] == "company" else real_get(doctype, *args, **kwargs)
            denied("snapshot", scope)
        previous = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        invoke("sync", {"passEvents": [{**scope, "localEventId": "yesterday", "occurredAt": previous}]})
        assert invoke("snapshot", scope)["pass"] == 2
        passed.append("validation_atomicity_company_fence_and_site_day")

        frappe.set_user("Administrator")
        email = "uqqc-" + uuid.uuid4().hex + "@example.invalid"
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "UQQC verification",
                               "enabled": 1, "send_welcome_email": 0, "user_type": "Website User",
                               "company": line.company,
                               "roles": [{"role": READER_ROLE}]}).insert(ignore_permissions=True).name
        assert invoke("snapshot", scope, auth="", session=user)["pass"] == 2
        denied("sync", batch, auth="", session=user)
        denied("snapshot", scope, auth="", session="Administrator")
        endpoint = frappe.db.get_value("API Documentation Endpoint", {"operation_id": "uqqc_snapshot"}, "name")
        frappe.db.set_value("API Documentation Endpoint", endpoint, "is_active", 0)
        denied("snapshot", scope)
        frappe.db.set_value("API Documentation Endpoint", endpoint, "is_active", 1)
        frappe.db.delete("API Documentation Endpoint Role", {"parent": endpoint})
        denied("snapshot", scope, auth="", session=user)
        assert invoke("snapshot", scope)["pass"] == 2
        passed.append("live_role_allowlist_and_device_auth_independence")
        assert not frappe.has_permission(api.EVENT_TYPE, "read", user=user)
        frappe.set_user("Administrator")
        from factory_management.api_docs import openapi
        contract = openapi("uqqc")
        assert len(contract["paths"]) == 6
        assert "UQQCDeviceToken" in contract["components"]["securitySchemes"]
        from factory_management.uqqc.provision import ensure_catalog, ensure_scripts
        from factory_management.uqqc.web_page import ensure_page
        script = frappe.get_doc("Server Script", "UQQC Bootstrap")
        script.script += "\n# UQQC verification"
        script.save(ignore_permissions=True)
        page = frappe.get_doc("Web Page", "uqqc")
        page.css += "\n/* UQQC verification */"
        page.save(ignore_permissions=True)
        ensure_catalog()
        ensure_scripts()
        ensure_page()
        assert frappe.db.get_value("Server Script", script.name, "script") == script.script
        assert frappe.db.get_value("Web Page", page.name, "css") == page.css
        assert not frappe.get_all("API Documentation Endpoint Role", filters={"parent": endpoint})
        from factory_management import qc_web_page, web_page_permissions
        other = frappe._dict(name="unrelated", route="unrelated")
        assert web_page_permissions.has_permission(other, "write", "Guest") == qc_web_page.has_web_page_permission(other, "write", "Guest")
        assert not web_page_permissions.has_permission(page, "write", "Guest")
        assert web_page_permissions.has_permission(page, "write", "Administrator")
        passed.append("catalog_page_permissions_and_preserved_desk_edits")

        suffix = uuid.uuid4().hex[:10]
        qc_group = frappe.db.get_value("QC Defect", {"is_active": 1, "record_type": "Group"}, "name")
        qc_position_group = frappe.db.get_value("QC Defect Position", {"is_active": 1, "record_type": "Group"}, "name")
        uqqc_group = frappe.db.get_value("UQQC Defect", {"is_active": 1, "record_type": "Group"}, "name")
        uqqc_position_group = frappe.db.get_value("UQQC Defect Position", {"is_active": 1, "record_type": "Group"}, "name")
        assert qc_group and qc_position_group and uqqc_group and uqqc_position_group
        qc_only_defect = frappe.get_doc({
            "doctype": "QC Defect", "record_type": "Defect", "code": "QC-" + suffix, "title": "QC only",
            "defect_group": qc_group, "is_active": 1,
        }).insert(ignore_permissions=True)
        qc_only_position = frappe.get_doc({
            "doctype": "QC Defect Position", "record_type": "Position", "code": "QC-" + suffix, "title": "QC only",
            "position_group": qc_position_group, "is_active": 1,
        }).insert(ignore_permissions=True)
        uqqc_only_defect = frappe.get_doc({
            "doctype": "UQQC Defect", "record_type": "Defect", "code": "UQ-" + suffix, "title": "UQQC only",
            "defect_group": uqqc_group, "is_active": 1,
        }).insert(ignore_permissions=True)
        uqqc_only_position = frappe.get_doc({
            "doctype": "UQQC Defect Position", "record_type": "Position", "code": "UQ-" + suffix, "title": "UQQC only",
            "position_group": uqqc_position_group, "is_active": 1,
        }).insert(ignore_permissions=True)
        qc_request = EnvironBuilder(path="/api/method/factory_management.api.bootstrap", method="GET",
                                    headers={"X-QC-Token": qc_secret})
        frappe.local.request = Request(qc_request.get_environ())
        qc_catalog = qc_api.bootstrap(device_id)["catalog"]
        qc_request.close()
        uqqc_catalog = invoke("bootstrap")
        assert qc_only_defect.name in {item["id"] for item in qc_catalog["defects"]}
        assert qc_only_position.name in {item["id"] for item in qc_catalog["defect_positions"]}
        assert qc_only_defect.name not in {item["id"] for item in uqqc_catalog["defects"]}
        assert qc_only_position.name not in {item["id"] for item in uqqc_catalog["defectPositions"]}
        assert uqqc_only_defect.name in {item["id"] for item in uqqc_catalog["defects"]}
        assert uqqc_only_position.name in {item["id"] for item in uqqc_catalog["defectPositions"]}
        assert uqqc_only_defect.name not in {item["id"] for item in qc_catalog["defects"]}
        assert uqqc_only_position.name not in {item["id"] for item in qc_catalog["defect_positions"]}
        denied("sync", {"events": [{**event, "localEventId": "qc-only-defect", "defectId": qc_only_defect.name}]})
        denied("sync", {"events": [{**event, "localEventId": "qc-only-position", "defectPositionId": qc_only_position.name}]})
        uqqc_event = {**event, "localEventId": "uqqc-only", "defectId": uqqc_only_defect.name,
                      "defectPositionId": uqqc_only_position.name}
        assert invoke("sync", {"events": [uqqc_event]})["acceptedCount"] == 1
        assert invoke("sync", {"events": [uqqc_event]})["acceptedCount"] == 1
        assert frappe.get_meta(api.EVENT_TYPE).get_field("defect").options == "UQQC Defect"
        assert frappe.get_meta(api.EVENT_TYPE).get_field("defect_position").options == "UQQC Defect Position"
        passed.append("independent_catalogs_and_offline_idempotency")

        catalog_manager = frappe.get_doc({
            "doctype": "User", "email": "uqqc-catalog-" + suffix + "@example.invalid",
            "first_name": "UQQC catalog verification", "enabled": 1,
            "send_welcome_email": 0, "user_type": "System User", "company": line.company,
            "roles": [{"role": CATALOG_MANAGER_ROLE}],
        }).insert(ignore_permissions=True).name
        assert frappe.has_permission("UQQC Defect", "write", user=catalog_manager)
        assert not frappe.has_permission("QC Defect", "write", user=catalog_manager)
        passed.append("catalog_manager_is_uqqc_only")
        return {"passed": passed, "temporary_data": "rolled_back"}
    finally:
        frappe.db.rollback(save_point="uqqc_verification")
        frappe.local.request = old_request
        frappe.local.form_dict = old_form
        frappe.local.response = old_response
        frappe.set_user(old_user)
        if user:
            frappe.clear_cache(user=user)
        if catalog_manager:
            frappe.clear_cache(user=catalog_manager)
