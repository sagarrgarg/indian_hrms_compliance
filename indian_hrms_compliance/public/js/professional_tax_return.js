// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// Phase 6B-2 — Professional Tax Return form add-ons.

frappe.ui.form.on("Professional Tax Return", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.filing_status === "Draft" || frm.doc.filing_status === "Generated") {
			const label =
				frm.doc.filing_status === "Generated"
					? __("Regenerate PT CSV")
					: __("Generate PT CSV");
			frm.add_custom_button(
				label,
				() => {
					const msg =
						frm.doc.filing_status === "Generated"
							? __("This will overwrite the rows + attached CSV. Continue?")
							: __("Generate PT rows from submitted Salary Slips in this period?");
					frappe.confirm(msg, () => {
						frappe.call({
							method: "indian_hrms_compliance.overrides.pt_return_generator.generate_pt_return",
							args: { pt_return_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Generating PT return..."),
							callback: (r) => {
								if (r.message) {
									frappe.show_alert({
										message: __(
											"Generated: {0} employees, ₹{1} PT collected ({2} variance flagged).",
											[
												r.message.total_employees_in_state,
												format_currency(r.message.total_pt_collected),
												r.message.variance_rows,
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
								label: __("Challan Number"),
								fieldname: "challan_number",
								fieldtype: "Data",
								description: __("State PT challan number after payment."),
							},
						],
						(values) => {
							frappe.call({
								method: "indian_hrms_compliance.overrides.pt_return_generator.mark_pt_return_filed",
								args: {
									pt_return_name: frm.doc.name,
									challan_number: values.challan_number || "",
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
						__("Mark PT Return as Filed"),
						__("Confirm")
					);
				},
				__("Phase 6B")
			);
		}

		if (frm.doc.pt_csv) {
			frm.add_custom_button(
				__("Download PT CSV"),
				() => window.open(frm.doc.pt_csv),
				__("View")
			);
		}
	},
});
