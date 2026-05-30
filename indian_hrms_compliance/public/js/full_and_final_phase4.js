// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// Phase 4 add-on for Full and Final Statement:
//  - "Generate Exit Letters" button on saved drafts.
//  - "Recompute Notice + TDS" button to re-trigger compute_phase4_lines
//    after editing dates / amounts / disposition without leaving the form.
frappe.ui.form.on("Full and Final Statement", {
	refresh(frm) {
		// Only show on saved (draft) docs — after Submit, the JE flow takes over.
		if (frm.is_new()) return;

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Recompute Notice + TDS"),
				() => frm.save(),
				__("Phase 4")
			);
			frm.add_custom_button(
				__("Generate Exit Letters"),
				() => {
					if (!frm.doc.relieving_date) {
						frappe.msgprint(__("Set Relieving Date first."));
						return;
					}
					frappe.call({
						method: "indian_hrms_compliance.overrides.full_and_final_extension.generate_exit_letters_from_fnf",
						args: { fnf_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Generating exit letters..."),
						callback: (r) => {
							if (r.message && r.message.length) {
								frappe.show_alert({
									message: __("Generated {0} letters. Open from the Appointment Letter list.", [r.message.length]),
									indicator: "green",
								});
							}
						},
					});
				},
				__("Phase 4")
			);
		}

		// Quick link from FnF to the linked Resignation Request.
		if (frm.doc.resignation_request) {
			frm.add_custom_button(
				__("Open Resignation Request"),
				() => frappe.set_route("Form", "Resignation Request", frm.doc.resignation_request),
				__("View")
			);
		}
	},
});
