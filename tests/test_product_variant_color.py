"""Offline checks for the Product Variant color migration."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


MIGRATION = Path(__file__).parents[1] / "factory_management" / "patches" / "use_product_variant_color.py"


class Row(dict):
    def __getattr__(self, name):
        return self[name]


class FakeDatabase:
    def __init__(self, rows, colors=("09", "10"), columns=("name", "qc_color", "color")):
        self.rows = {row["name"]: dict(row) for row in rows}
        self.colors = set(colors)
        self.columns = set(columns)
        self.ddl = []
        self.custom_field = True

    def exists(self, doctype, name):
        if doctype == "DocType":
            return name == "Product Variant"
        if doctype == "Product Color":
            return name in self.colors
        if doctype == "Custom Field" and isinstance(name, dict):
            return False
        return False

    def table_exists(self, doctype, cached=False):
        return doctype == "Product Variant"

    def get_table_columns(self, doctype):
        return tuple(self.columns)

    def sql(self, query, values=None, as_dict=False):
        if query.startswith("SELECT"):
            fields = [field.strip(" `") for field in query.split(" FROM ")[0][len("SELECT "):].split(",")]
            return [Row({field: row.get(field) for field in fields}) for row in self.rows.values()]
        if query.startswith("UPDATE"):
            value, name = values
            self.rows[name]["product_color"] = value
            return None
        raise AssertionError(query)

    def sql_ddl(self, query):
        self.ddl.append(query)
        field = query.split("`")[-2]
        if "ADD COLUMN" in query:
            self.columns.add(field)
            for row in self.rows.values():
                row[field] = None
        elif "DROP COLUMN" in query:
            self.columns.remove(field)
            for row in self.rows.values():
                row.pop(field, None)
        else:
            raise AssertionError(query)


def load_migration(database, fields=None):
    frappe = types.ModuleType("frappe")
    frappe.db = database
    frappe.ValidationError = type("ValidationError", (Exception,), {})
    frappe.throw = lambda text, kind: (_ for _ in ()).throw(kind(text))
    frappe.get_doc = lambda doctype, name: types.SimpleNamespace(fields=fields or [
        types.SimpleNamespace(fieldname="product_color", fieldtype="Link", options="Product Color"),
    ])
    frappe.get_all = lambda doctype, **kwargs: (
        ["Product Variant-qc_color"] if doctype == "Custom Field" and database.custom_field else []
    )
    frappe.delete_doc = lambda doctype, name, **kwargs: setattr(database, "custom_field", False)
    frappe.clear_cache = lambda **kwargs: None
    registry = types.ModuleType("factory_management.device_registry")
    registry.message = lambda key: key + " {count} {records}"
    package = types.ModuleType("factory_management")
    patches = types.ModuleType("factory_management.patches")
    with patch.dict(sys.modules, {
        "frappe": frappe,
        "factory_management": package,
        "factory_management.patches": patches,
        "factory_management.device_registry": registry,
    }):
        spec = importlib.util.spec_from_file_location("product_variant_color_under_test", MIGRATION)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, frappe


class ProductVariantColorMigrationTests(unittest.TestCase):
    def test_moves_qc_color_and_removes_legacy_columns(self):
        database = FakeDatabase([{"name": "variant-1", "qc_color": "09", "color": None}])
        migration, _ = load_migration(database)
        migration.prepare()
        self.assertEqual(database.rows["variant-1"]["product_color"], "09")
        migration.finalize()
        self.assertEqual(database.columns, {"name", "product_color"})
        self.assertFalse(database.custom_field)
        migration.prepare()
        migration.finalize()
        self.assertEqual(database.rows["variant-1"]["product_color"], "09")

    def test_maps_exact_legacy_color_name(self):
        database = FakeDatabase([{"name": "variant-1", "qc_color": None, "color": "09"}])
        migration, _ = load_migration(database)
        migration.prepare()
        self.assertEqual(database.rows["variant-1"]["product_color"], "09")

    def test_conflicting_fields_stop_before_schema_change(self):
        database = FakeDatabase([{"name": "variant-1", "qc_color": "09", "color": "10"}])
        migration, frappe = load_migration(database)
        with self.assertRaises(frappe.ValidationError):
            migration.prepare()
        self.assertEqual(database.ddl, [])
        self.assertNotIn("product_color", database.rows["variant-1"])

    def test_unknown_legacy_color_stops_before_schema_change(self):
        database = FakeDatabase([{"name": "variant-1", "qc_color": None, "color": "red"}])
        migration, frappe = load_migration(database)
        with self.assertRaises(frappe.ValidationError):
            migration.prepare()
        self.assertEqual(database.ddl, [])

    def test_existing_new_value_must_match_old_value(self):
        database = FakeDatabase(
            [{"name": "variant-1", "qc_color": "09", "color": None, "product_color": "10"}],
            columns=("name", "qc_color", "color", "product_color"),
        )
        migration, frappe = load_migration(database)
        with self.assertRaises(frappe.ValidationError):
            migration.prepare()
        self.assertEqual(database.ddl, [])

    def test_finalize_requires_new_link_field(self):
        database = FakeDatabase([{"name": "variant-1", "qc_color": "09", "color": None}])
        migration, frappe = load_migration(database, fields=[
            types.SimpleNamespace(fieldname="color", fieldtype="Link", options="Color"),
        ])
        migration.prepare()
        with self.assertRaises(frappe.ValidationError):
            migration.finalize()
        self.assertTrue(database.custom_field)
        self.assertIn("qc_color", database.columns)


if __name__ == "__main__":
    unittest.main()
