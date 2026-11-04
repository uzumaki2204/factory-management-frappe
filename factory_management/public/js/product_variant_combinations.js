(() => {
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

	async function linkedRecords(doctype, names, fields) {
		const uniqueNames = [...new Set(names.filter(Boolean))];
		if (!uniqueNames.length) return new Map();

		const rows = await frappe.db.get_list(doctype, {
			filters: { name: ["in", uniqueNames] },
			fields: ["name", ...fields],
			limit_page_length: uniqueNames.length,
		});
		return new Map(rows.map((row) => [row.name, row]));
	}

	function recordLabel(record, fallback, fields) {
		if (!record) return fallback || __("Not set");
		const label = fields.map((field) => record[field]).find(Boolean);
		return label || record.name || fallback || __("Not set");
	}

	function renderTable(rows, markets, colors, sizes) {
		if (!rows.length) return renderMessage(__("No variants found for this product."));

		const compare = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" }).compare;
		const sortedRows = [...rows].sort((left, right) => {
			const marketOrder = compare(markets.get(left.market)?.code || left.market || "", markets.get(right.market)?.code || right.market || "");
			if (marketOrder) return marketOrder;
			const colorOrder = compare(colors.get(left.product_color)?.color_code || left.product_color || "", colors.get(right.product_color)?.color_code || right.product_color || "");
			if (colorOrder) return colorOrder;
			const sizeOrder = Number(sizes.get(left.size)?.sort_order || 0) - Number(sizes.get(right.size)?.sort_order || 0);
			return sizeOrder || compare(sizes.get(left.size)?.size_label || left.size || "", sizes.get(right.size)?.size_label || right.size || "");
		});
		const body = sortedRows
			.map((row) => {
				const market = recordLabel(markets.get(row.market), row.market, ["name_en", "code"]);
				const color = recordLabel(colors.get(row.product_color), row.product_color, ["color_name", "color_code"]);
				const size = recordLabel(sizes.get(row.size), row.size, ["size_label", "size_code"]);
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

			const [markets, colors, sizes] = await Promise.all([
				linkedRecords("Market", rows.map((row) => row.market), ["code", "name_en"]),
				linkedRecords("Product Color", rows.map((row) => row.product_color), ["color_code", "color_name"]),
				linkedRecords("ProductSize", rows.map((row) => row.size), ["size_code", "size_label", "sort_order"]),
			]);

			if (frm.__variant_combinations_request === requestId) {
				render(frm, renderTable(rows, markets, colors, sizes));
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
