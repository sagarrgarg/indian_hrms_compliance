// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// Phase 6B-2 — TDS Return Form 24Q form add-ons.
//
//   - "Generate" / "Regenerate" — builds Annexure I (+ II for Q4) +
//     the RPU .txt and attaches it.
//   - "Mark as Filed" — prompts for the 15-digit RPU acknowledgement
//     number; required to flip status.
//   - "Download RPU File" — quick link when txt_file is attached.

frappe.ui.form.on("TDS Return Form 24Q", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.filing_status === "Draft" || frm.doc.filing_status === "Generated") {
			const label =
				frm.doc.filing_status === "Generated"
					? __("Regenerate")
					: __("Generate");
			frm.add_custom_button(
				label,
				() => {
					const msg =
						frm.doc.filing_status === "Generated"
							? __("This will overwrite Annexure rows + the attached RPU file. Continue?")
							: __("Generate Annexure I (and II if Q4) from submitted Salary Slips?");
					frappe.confirm(msg, () => {
						frappe.call({
							method: "indian_hrms_compliance.overrides.form_24q_generator.generate_form_24q",
							args: { form_24q_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Generating TDS return..."),
							callback: (r) => {
								if (r.message) {
									frappe.show_alert({
										message: __(
											"Generated: {0} deductees, ₹{1} TDS, {2} Annex II rows.",
											[
												r.message.annexure_i_count,
												format_currency(r.message.total_tax_deducted),
												r.message.annexure_ii_count,
											]
										),
										indicator: "green",
									});
									frm.reload_doc();
								}
							},
						});
					});
				},
				__("Phase 6B")
			);
		}

		if (frm.doc.filing_status === "Generated") {
			frm.add_custom_button(
				__("Mark as Filed"),
				() => {
					frappe.prompt(
						[
							{
								label: __("Acknowledgement Number"),
								fieldname: "ack_number",
								fieldtype: "Data",
								reqd: 1,
								description: __(
									"15-digit RPU acknowledgement number issued by NSDL TIN after .fvu upload."
								),
							},
						],
						(values) => {
							frappe.call({
								method: "indian_hrms_compliance.overrides.form_24q_generator.mark_form_24q_filed",
								args: {
									form_24q_name: frm.doc.name,
									ack_number: values.ack_number,
								},
								freeze: true,
								callback: () => {
									frappe.show_alert({
										message: __("Marked as Filed."),
										indicator: "green",
									});
									frm.reload_doc();
								},
							});
						},
						__("Mark TDS Return as Filed"),
						__("Confirm")
					);
				},
				__("Phase 6B")
			);
		}

		if (frm.doc.txt_file) {
			frm.add_custom_button(
				__("Download RPU File"),
				() => window.open(frm.doc.txt_file),
				__("View")
			);
		}
	},
});
