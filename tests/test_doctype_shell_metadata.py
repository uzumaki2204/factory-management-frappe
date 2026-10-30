"""Fresh installs must not reference title fields before fields are synced."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class DocTypeShellTests(unittest.TestCase):
    def test_empty_shells_have_valid_naming_and_no_dangling_title_field(self):
        shells = []
        frappe = types.ModuleType("frappe")
        frappe.db = types.SimpleNamespace(exists=lambda *args: False)

        def get_doc(values):
            def insert(**kwargs):
                self.assertFalse(values["fields"])
                self.assertNotIn("title_field", values)
                self.assertFalse(values["show_title_field_in_link"])
                self.assertEqual(values["autoname"], "hash")
                shells.append(values["name"])
            return types.SimpleNamespace(insert=insert)

        frappe.get_doc = get_doc
        source = Path(__file__).parents[1] / "factory_management/install.py"
        with patch.dict(sys.modules, {"frappe": frappe}):
            spec = importlib.util.spec_from_file_location("doctype_shell_installer_under_test", source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module._ensure_snapshot_doctype_shells()
        self.assertTrue({"Factory Device", "UQQC Defect", "UQQC Defect Position"}.issubset(shells))


if __name__ == "__main__":
    unittest.main()
