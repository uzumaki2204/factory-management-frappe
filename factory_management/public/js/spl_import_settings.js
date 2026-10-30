const SPL_STATUS_OPTIONS = {
	answer_status_id: [
		{ code: "0001", label: "Accepted" },
		{ code: "0002", label: "Rejected" },
		{ code: "0003", label: "Not Answered" },
		{ code: "0004", label: "Not Answered (FR Updating)" },
		{ code: "0005", label: "Not Required" },
	],
	document_status_ids: [
		{ code: "0001", label: "New" },
		{ code: "0002", label: "Change" },
		{ code: "0003", label: "Cancel" },
		{ code: "0004", label: "Finalized" },
		{ code: "0005", label: "FR Updating" },
	],
};

const SPL_STATUS_GROUP_LABELS = {
	answer_status_id: "Answer Status",
	document_status_ids: "Document Status",
};

function spl_status_codes(value) {
	return [...new Set(String(value || "")
		.split(",")
		.map((code) => code.trim())
		.filter(Boolean))];
}

function spl_escape_html(value) {
	return frappe.utils.escape_html(String(value || ""));
}

function spl_status_group_html(fieldname, selectedCodes) {
	const options = [...SPL_STATUS_OPTIONS[fieldname]];
	const knownCodes = new Set(options.map((option) => option.code));
	const unknownCodes = selectedCodes.filter((code) => !knownCodes.has(code));
	unknownCodes.forEach((code) => options.push({ code, label: __("Unknown status") }));
	const label = __(SPL_STATUS_GROUP_LABELS[fieldname]);
	const safeFieldname = spl_escape_html(fieldname);
	const optionMarkup = options
		.map((option) => {
			const checked = selectedCodes.includes(option.code) ? " checked" : "";
			const inputId = `spl-status-${fieldname}-${option.code}`;
			return `<label class="spl-status-option" for="${spl_escape_html(inputId)}">
				<input class="spl-status-option__check" id="${spl_escape_html(inputId)}" type="checkbox" data-spl-status-checkbox="${safeFieldname}" value="${spl_escape_html(option.code)}"${checked}>
				<span class="spl-status-option__text"><strong>${spl_escape_html(option.code)}</strong><span>${spl_escape_html(__(option.label))}</span></span>
			</label>`;
		})
		.join("");

	return `<section class="spl-status-card" aria-labelledby="spl-status-title-${safeFieldname}">
		<header class="spl-status-card__header">
			<h3 class="spl-status-card__title" id="spl-status-title-${safeFieldname}">${spl_escape_html(label)}</h3>
			<div class="spl-status-card__actions">
				<button class="btn btn-xs btn-default" type="button" data-spl-status-action="all" data-spl-status-field="${safeFieldname}">${spl_escape_html(__("Select all"))}</button>
				<button class="btn btn-xs btn-default" type="button" data-spl-status-action="clear" data-spl-status-field="${safeFieldname}">${spl_escape_html(__("Clear selection"))}</button>
			</div>
		</header>
		<div class="spl-status-card__options">${optionMarkup}</div>
	</section>`;
}

function spl_sync_status_field(frm, wrapper, fieldname) {
	const codes = wrapper
		.find(`[data-spl-status-checkbox="${fieldname}"]:checked`)
		.map((_, input) => input.value)
		.get();
	return frm.set_value(fieldname, codes.join(","));
}

function spl_render_status_filters(frm) {
	const field = frm.fields_dict.status_filter_selector;
	if (!field || !field.$wrapper) return;

	const wrapper = field.$wrapper;
	const answerCodes = spl_status_codes(frm.doc.answer_status_id);
	const documentCodes = spl_status_codes(frm.doc.document_status_ids);
	wrapper.html(`<div class="spl-status-filter-grid">
		${spl_status_group_html("answer_status_id", answerCodes)}
		${spl_status_group_html("document_status_ids", documentCodes)}
	</div>`);

	wrapper.off(".splStatusFilter");
	wrapper.on("change.splStatusFilter", "[data-spl-status-checkbox]", function () {
		spl_sync_status_field(frm, wrapper, this.dataset.splStatusCheckbox);
	});
	wrapper.on("click.splStatusFilter", "[data-spl-status-action]", function () {
		const fieldname = this.dataset.splStatusField;
		const checked = this.dataset.splStatusAction === "all";
		wrapper.find(`[data-spl-status-checkbox="${fieldname}"]`).prop("checked", checked);
		spl_sync_status_field(frm, wrapper, fieldname);
	});
}

frappe.ui.form.on("SPL Import Settings", {
	refresh(frm) {
		spl_render_status_filters(frm);
	},
});
