"""Offline safety checks for the Factory Device identity migration."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PATCH = Path(__file__).parents[1] / "factory_management" / "patches" / "use_factory_device_record_id.py"
DEVICE = "Factory Device"
CLIENT = "Factory Device Client"
IDENTITY = "9d2f8a5c-36c4-4c14-86a1-947186559c44"


class FakeDatabase:
    def __init__(self, rows, columns=("name", "device_id", "device_uid"), client=False,
                 legacy_client_map=False):
        self.rows = rows
        self.columns = columns
        self.client = client
        self.legacy_client_map = legacy_client_map
        self.statements = []

    def exists(self, doctype, name):
        return doctype == "DocType" and (
            name == DEVICE or (name == CLIENT and self.client)
            or (name == "QC Legacy Map" and self.legacy_client_map))

    def table_exists(self, doctype, cached=False):
        return doctype == DEVICE or (doctype == CLIENT and self.client)

    def get_table_columns(self, doctype):
        return self.columns

    def sql(self, query, as_dict=False):
        return [types.SimpleNamespace(**row) for row in self.rows]

    def count(self, doctype, filters):
        return int(doctype == "QC Legacy Map" and self.legacy_client_map
                   and filters.get("target_doctype") == CLIENT)

    def sql_ddl(self, query):
        self.statements.append(query)


def load_patch(db):
    frappe = types.ModuleType("frappe")
    frappe.db = db
    frappe.ValidationError = type("ValidationError", (Exception,), {})
    frappe.throw = lambda message, kind: (_ for _ in ()).throw(kind(message))
    frappe.get_all = lambda *args, **kwargs: []
    frappe.clear_cache = lambda **kwargs: None
    registry = types.ModuleType("factory_management.device_registry")
    registry.CLIENT_TYPE = CLIENT
    registry.DEVICE_TYPE = DEVICE
    registry.message = lambda key: key + ":{device}"
    install = types.ModuleType("factory_management.install")
    install.ensure_device_schema = lambda: None
    package = types.ModuleType("factory_management")
    modules = {
        "frappe": frappe, "factory_management": package,
        "factory_management.device_registry": registry,
        "factory_management.install": install,
    }
    with patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("device_id_migration_under_test", PATCH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, frappe


class DeviceIdentityMigrationTests(unittest.TestCase):
    def test_mismatched_legacy_id_stops_before_ddl(self):
        db = FakeDatabase([{"name": IDENTITY, "device_id": "different"}])
        migration, frappe = load_patch(db)
        with self.assertRaises(frappe.ValidationError):
            migration.execute()
        self.assertEqual(db.statements, [])

    def test_invalid_uuid_stops_before_ddl(self):
        db = FakeDatabase([{"name": "not-a-uuid", "device_id": "not-a-uuid"}])
        migration, frappe = load_patch(db)
        with self.assertRaises(frappe.ValidationError):
            migration.execute()
        self.assertEqual(db.statements, [])

    def test_noncanonical_uuid_stops_before_ddl(self):
        name = IDENTITY.replace("-", "")
        db = FakeDatabase([{"name": name, "device_id": name}])
        migration, frappe = load_patch(db)
        with self.assertRaises(frappe.ValidationError):
            migration.execute()
        self.assertEqual(db.statements, [])

    def test_client_legacy_map_stops_before_ddl(self):
        db = FakeDatabase([{"name": IDENTITY, "device_id": IDENTITY}], client=True,
                          legacy_client_map=True)
        migration, frappe = load_patch(db)
        with self.assertRaises(frappe.ValidationError):
            migration.execute()
        self.assertEqual(db.statements, [])

    def test_preflight_accepts_aligned_identity_and_repeat_without_legacy_columns(self):
        first, _ = load_patch(FakeDatabase([{"name": IDENTITY, "device_id": IDENTITY}]))
        first._preflight()
        second, _ = load_patch(FakeDatabase([{"name": IDENTITY}], columns=("name",)))
        second._preflight()


if __name__ == "__main__":
    unittest.main()
