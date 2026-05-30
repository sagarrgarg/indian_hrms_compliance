// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// Phase 6B-1 — ESI Half Yearly Return form add-ons.

frappe.ui.form.on("ESI Half Yearly Return", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(
			__("Aggregate Monthly Filings"),
			() => {
				frappe.call({
					method: "indian_hrms_compliance.overrides.esi_half_yearly_aggregator.aggregate_esi_half_yearly",
					args: { esi_hy_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Aggregating linked ESI Monthly Contributions..."),
					callback: (r) => {
						if (r.message) {
							frappe.show_alert({
								message: __("Linked {0} monthly filing(s). Total contribution: ₹{1}.", [
									r.message.months_linked,
									format_currency(r.message.total_contribution_period),
								]),
								indicator: "green",
							});
							frm.reload_doc();
						}
					},
				});
			},
			__("Phase 6B")
		);

		if (frm.doc.summary_html) {
			// Render the summary HTML into a wrapper if a html_render area exists.
			const wrapper = frm.fields_dict.summary_html?.$wrapper;
			if (wrapper) {
				wrapper.find(".preview").remove();
				wrapper.append(`<div class="preview" style="margin-top:8px">${frm.doc.summary_html}</div>`);
			}
		}
	},
});
