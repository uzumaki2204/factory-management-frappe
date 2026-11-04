(() => {
	if (window.__factoryProductVariantCombinationsRegistered) return;
	window.__factoryProductVariantCombinationsRegistered = true;

	const FIELDNAME = "variant_combinations";

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

	function renderGroup(title, values) {
		const chips = values.length
			? values.map((item) => `<span class="badge rounded-pill bg-light text-dark border">${escape(item.label)}</span>`).join("")
			: "";
		return `<section class="mb-3">
			<p class="text-muted mb-2">${escape(title)}</p>
			<div class="d-flex flex-wrap gap-2">${chips}</div>
		</section>`;
	}

	function renderGroups(payload) {
		if (!payload.total_variants) return renderMessage(__("No variants found for this product."));

		const groups = payload.groups || {};
		const colors = [...(groups.colors || [])];
		const sizes = [...(groups.sizes || [])];
		const markets = [...(groups.markets || [])];
		const compare = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" }).compare;
		for (const values of [colors, sizes, markets]) {
			values.sort((left, right) => compare(left.label || "", right.label || ""));
		}
		if (payload.has_unset_color) colors.push({ id: "", label: __("Not Applicable") });
		if (payload.has_unset_size) sizes.push({ id: "", label: __("Not Applicable") });

		return `${renderGroup(__("Markets selected: {0}", [markets.length]), markets)}
			${renderGroup(__("Colors selected: {0}", [colors.length]), colors)}
			${renderGroup(__("Sizes selected: {0}", [sizes.length]), sizes)}`;
	}

	async function loadVariants(frm, requestId) {
		if (frm.is_new()) {
			render(frm, renderMessage(__("Save the product to view its variant combinations.")));
			return;
		}

		render(frm, renderMessage(__("Loading variant combinations...")));
		try {
			const response = await frappe.call({
				method: "factory_management.api.product_variant_groups",
				args: { product: frm.doc.name },
			});

			if (frm.__variant_combinations_request === requestId) {
				const payload = response && response.message ? response.message : response;
				render(frm, renderGroups(payload || {}));
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
