(() => {
	if (window.__factoryProductVariantCombinationsRegistered) return;
	window.__factoryProductVariantCombinationsRegistered = true;

	const FIELDNAME = "variant_combinations";
	const PAGE_SIZE = 5000;

	function escape(value) {
		return frappe.utils.escape_html(String(value || ""));
	}

	function render(frm, html) {
		const field = frm.fields_dict[FIELDNAME];
		if (field && field.$wrapper) field.$wrapper.html(html);
	}

	function renderMessage(text, kind = "text-muted") {
		return `<p class="${kind}">${escape(text)}</p>`;
	}

	function renderTable(rows) {
		if (!rows.length) return renderMessage(__("No variants found for this product."));

		const compare = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" }).compare;
		const sortedRows = [...rows].sort((left, right) => {
			const marketOrder = compare(left.market || "", right.market || "");
			if (marketOrder) return marketOrder;
			const colorOrder = compare(left.product_color || "", right.product_color || "");
			if (colorOrder) return colorOrder;
			return compare(left.size || "", right.size || "");
		});
		const body = sortedRows
			.map((row) => {
				const market = row.market || __("Not set");
				const color = row.product_color || __("Not set");
				const size = row.size || __("Not set");
				const status = row.is_active ? __("Active") : __("Inactive");
				return `<tr>
					<td>${escape(market)}</td>
					<td>${escape(color)}</td>
					<td>${escape(size)}</td>
					<td>${escape(status)}</td>
				</tr>`;
			})
			.join("");

		return `<p class="text-muted">${escape(__("Total variants: {0}", [rows.length]))}</p>
			<div class="table-responsive">
				<table class="table table-bordered" aria-label="${escape(__("Variant Combinations"))}">
					<thead><tr>
						<th scope="col">${escape(__("Market"))}</th>
						<th scope="col">${escape(__("Color"))}</th>
						<th scope="col">${escape(__("Size"))}</th>
						<th scope="col">${escape(__("Status"))}</th>
					</tr></thead>
					<tbody>${body}</tbody>
				</table>
			</div>`;
	}

	async function loadVariants(frm, requestId) {
		if (frm.is_new()) {
			render(frm, renderMessage(__("Save the product to view its variant combinations.")));
			return;
		}

		render(frm, renderMessage(__("Loading variant combinations...")));
		try {
			const rows = await frappe.db.get_list("Product Variant", {
				filters: { product: frm.doc.name },
				fields: ["name", "market", "product_color", "size", "is_active"],
				order_by: "market asc, product_color asc, size asc",
				limit_page_length: PAGE_SIZE,
			});

			if (frm.__variant_combinations_request === requestId) {
				render(frm, renderTable(rows));
			}
		} catch (_error) {
			if (frm.__variant_combinations_request === requestId) {
				render(frm, renderMessage(__("Unable to load variant combinations."), "text-danger"));
			}
		}
	}

	frappe.ui.form.on("Product", {
		refresh(frm) {
			frm.__variant_combinations_request = (frm.__variant_combinations_request || 0) + 1;
			loadVariants(frm, frm.__variant_combinations_request);
		},
	});
})();
