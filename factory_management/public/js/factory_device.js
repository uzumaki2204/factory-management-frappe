// Factory Device is a Custom DocType, so load through app_include_js.
frappe.ui.form.on("Factory Device", {
	setup(frm) {
		frm.set_query("factory", () => ({
			filters: frm.doc.company ? { company: frm.doc.company } : { name: ["=", ""] },
		}));
		frm.set_query("line", () => ({
			filters: frm.doc.factory ? { factory: frm.doc.factory } : { name: ["=", ""] },
		}));
	},
	company(frm) {
		return frm.set_value({ factory: null, line: null });
	},
	factory(frm) {
		return frm.set_value("line", null);
	},
});
