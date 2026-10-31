(() => {
	const ROW_CARD_SELECTOR = ".diw-warning-group .skip-row-btn";
	const BULK_BUTTON_SELECTOR = "[data-uqqc-skip-rows]";

	function rowsFromButton(button) {
		try {
			return [...new Set(JSON.parse(button.dataset.uqqcSkipRows || "[]"))]
				.map(Number)
				.filter(Number.isSafeInteger)
				.sort((a, b) => a - b);
		} catch (_error) {
			return [];
		}
	}

	function rowsFromAttribute(value) {
		try {
			return [...new Set(JSON.parse(value || "[]"))]
				.map(Number)
				.filter(Number.isSafeInteger)
				.sort((a, b) => a - b);
		} catch (_error) {
			return [];
		}
	}

	function makeSkipButton(label, rows, extraClass) {
		const button = document.createElement("button");
		button.type = "button";
		button.className = `btn btn-xs btn-default ${extraClass}`;
		button.dataset.uqqcSkipRows = JSON.stringify(rows);
		button.textContent = label;
		button.setAttribute("aria-label", label);
		return button;
	}

	function skippedRowNumbers(frm) {
		return new Set((frm.doc.skipped_rows || []).map((row) => Number(row.row_number)));
	}

	function currentPreviewData(frm, args) {
		if (args[1]) return args[1];
		if (frm.import_preview?.data_import_name === frm.doc.name) {
			return frm.import_preview.preview_data;
		}
		return null;
	}

	function renderBulkSkipControls(frm) {
		const field = frm.get_field("import_warnings");
		const wrapper = field?.$wrapper?.get(0);
		if (!wrapper) return;

		const rowCards = [...wrapper.querySelectorAll(ROW_CARD_SELECTOR)]
			.map((button) => button.closest(".warning[data-row]"))
			.filter(Boolean);
		const existingGroups = [...wrapper.querySelectorAll(".diw-warning-group .uqqc-row-warning-group")];
		if (!rowCards.length && !existingGroups.length) return;

		const rowGroup = rowCards[0]?.closest(".diw-warning-group") || existingGroups[0]?.closest(".diw-warning-group");
		const title = rowGroup?.querySelector(".diw-warning-group-title");
		if (!rowGroup || !title) return;

		const allRows = [...new Set([
			...rowCards.map((card) => Number(card.dataset.row)),
			...existingGroups.flatMap((card) => rowsFromAttribute(card.dataset.rows)),
		])]
			.filter(Number.isSafeInteger)
			.sort((a, b) => a - b);
		if (!allRows.length) return;

		const skipped = skippedRowNumbers(frm);
		const allSkipped = allRows.every((row) => skipped.has(row));
		for (const groupCard of existingGroups) {
			const rows = rowsFromAttribute(groupCard.dataset.rows);
			const button = groupCard.querySelector(".uqqc-skip-row-group");
			if (!button || !rows.length) continue;
			const groupSkipped = rows.every((row) => skipped.has(row));
			groupCard.classList.toggle("skipped", groupSkipped);
			button.textContent = groupSkipped
				? __("Undo skip for these rows ({0})", [rows.length])
				: __("Skip these rows ({0})", [rows.length]);
			button.setAttribute("aria-label", button.textContent);
		}
		title.classList.add("flex", "items-center", "justify-between", "gap-3");
		title.querySelectorAll(".uqqc-skip-all-rows").forEach((button) => button.remove());
		title.append(
			makeSkipButton(
				allSkipped
					? __("Undo skip for all rows ({0})", [allRows.length])
					: __("Skip all rows with issues ({0})", [allRows.length]),
				allRows,
				"uqqc-skip-all-rows"
			)
		);

		if (rowCards.length) {
			const issues = new Map();
			for (const card of rowCards) {
				const row = Number(card.dataset.row);
				const body = card.querySelector(".body");
				const messages = [...(body?.querySelectorAll("li") || [])];
				if (!messages.length && body) messages.push(body);
				for (const message of messages) {
					const key = (message.textContent || "").replace(/\s+/g, " ").trim();
					if (!key) continue;
					if (!issues.has(key)) issues.set(key, { message: message.cloneNode(true), rows: new Set() });
					issues.get(key).rows.add(row);
				}
			}

			const container = rowCards[0].parentElement;
			const anchor = rowCards[0];
			const orderedIssues = [...issues.values()].sort((left, right) => {
				const leftRow = Math.min(...left.rows);
				const rightRow = Math.min(...right.rows);
				return leftRow - rightRow || left.message.textContent.localeCompare(right.message.textContent);
			});
			for (const issue of orderedIssues) {
				const rows = [...issue.rows].sort((a, b) => a - b);
				const groupCard = document.createElement("div");
				groupCard.className = "warning relative m-0 p-0 border-0 bg-transparent uqqc-row-warning-group";
				groupCard.dataset.rows = JSON.stringify(rows);

				const header = document.createElement("div");
				header.className = "warning-row-header flex items-center justify-between gap-3 mb-1";
				const label = document.createElement("span");
				label.className = "text-base-semibold text-ink-gray-9";
				label.textContent = rows.length > 1
					? __("Rows with the same issue ({0})", [rows.length])
					: __("Row {0}", [rows[0]]);
				const groupSkipped = rows.every((row) => skipped.has(row));
				const groupButton = makeSkipButton(
					rows.length > 1
						? groupSkipped
							? __("Undo skip for these rows ({0})", [rows.length])
							: __("Skip these rows ({0})", [rows.length])
						: groupSkipped
							? __("Undo Skip")
							: __("Skip Row"),
					rows,
					"uqqc-skip-row-group"
				);
				groupCard.classList.toggle("skipped", groupSkipped);
				header.append(label, groupButton);
				const groupBody = document.createElement("div");
				groupBody.className = "body";
				const messageList = document.createElement("ul");
				messageList.className = "list-none m-0 p-0 flex flex-col gap-1";
				messageList.append(issue.message);
				groupBody.append(messageList);
				groupCard.append(header, groupBody);
				container.insertBefore(groupCard, anchor);
			}
			rowCards.forEach((card) => card.remove());
		}

		const $wrapper = field.$wrapper;
		$wrapper.off("click.uqqcBulkSkip", BULK_BUTTON_SELECTOR);
		$wrapper.on("click.uqqcBulkSkip", BULK_BUTTON_SELECTOR, function (event) {
			event.preventDefault();
			const rows = rowsFromButton(this);
			if (rows.length && typeof frm.events.toggle_skip_rows === "function") {
				frm.events.toggle_skip_rows(frm, rows);
			}
		});
	}

	function installRenderer(frm) {
		const original = frm.events?.render_import_warnings;
		if (typeof original !== "function" || original.uqqcBulkSkipWrapped) return;

		const wrapped = function (...args) {
			const previewData = currentPreviewData(frm, args);
			if (frm.doc.reference_doctype === "UQQC Inspection Event" && previewData?.warnings) {
				// Recompute from the current preview; persisted warnings may use the old
				// one-row summary format and would duplicate the grouped messages.
				frm.doc.template_warnings = "";
			}
			const result = original.apply(this, args);
			renderBulkSkipControls(frm);
			return result;
		};
		wrapped.uqqcBulkSkipWrapped = true;
		frm.events.render_import_warnings = wrapped;
		frm._uqqcBulkSkipRenderer = wrapped;
	}

	frappe.ui.form.on("Data Import", {
		refresh(frm) {
			installRenderer(frm);
			renderBulkSkipControls(frm);
		},
	});
})();
