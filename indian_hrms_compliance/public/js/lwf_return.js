// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// Phase 6B-2 — LWF Return form add-ons.

frappe.ui.form.on("LWF Return", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.filing_status === "Draft" || frm.doc.filing_status === "Generated") {
			const label =
				frm.doc.filing_status === "Generated"
					? __("Regenerate LWF CSV")
					: __("Generate LWF CSV");
			frm.add_custom_button(
				label,
				() => {
					const msg =
						frm.doc.filing_status === "Generated"
							? __("This will overwrite the rows + attached CSV. Continue?")
							: __("Generate LWF rows from submitted Salary Slips in this period?");
					frappe.confirm(msg, () => {
						frappe.call({
							method: "indian_hrms_compliance.overrides.lwf_return_generator.generate_lwf_return",
							args: { lwf_return_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Generating LWF return..."),
							callback: (r) => {
								if (r.message) {
									frappe.show_alert({
										message: __(
											"Generated: {0} employees, ₹{1} total LWF.",
											[
												r.message.total_employees,
												format_currency(r.message.total_contribution),
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
					frappe.call({
						method: "indian_hrms_compliance.overrides.lwf_return_generator.mark_lwf_return_filed",
						args: { lwf_return_name: frm.doc.name },
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
				__("Phase 6B")
			);
		}

		if (frm.doc.lwf_csv) {
			frm.add_custom_button(
				__("Download LWF CSV"),
				() => window.open(frm.doc.lwf_csv),
				__("View")
			);
		}
	},
});
