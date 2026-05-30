// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// Phase 6B-1 — ESI Monthly Contribution form add-ons.

frappe.ui.form.on("ESI Monthly Contribution", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.filing_status === "Draft" || frm.doc.filing_status === "Generated") {
			const label =
				frm.doc.filing_status === "Generated"
					? __("Regenerate Contribution File")
					: __("Generate Contribution File");
			frm.add_custom_button(
				label,
				() => {
					frappe.confirm(
						frm.doc.filing_status === "Generated"
							? __("This will overwrite existing rows + the attached CSV. Continue?")
							: __("Generate the ESI contribution file from submitted Salary Slips?"),
						() => {
							frappe.call({
								method: "indian_hrms_compliance.overrides.esi_generator.generate_esi_monthly",
								args: { esi_monthly_name: frm.doc.name },
								freeze: true,
								freeze_message: __("Generating ESI contribution file..."),
								callback: (r) => {
									if (r.message) {
										frappe.show_alert({
											message: __("ESI file generated: {0} IPs, challan ₹{1}.", [
												r.message.total_ips,
												format_currency(r.message.total_contribution),
											]),
											indicator: "green",
										});
										frm.reload_doc();
									}
								},
							});
						}
					);
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
								description: __("Enter the ESIC challan number after payment."),
							},
						],
						(values) => {
							frappe.call({
								method: "indian_hrms_compliance.overrides.esi_generator.mark_esi_filed",
								args: {
									esi_monthly_name: frm.doc.name,
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
						__("Mark ESI Contribution as Filed"),
						__("Confirm")
					);
				},
				__("Phase 6B")
			);
		}

		if (frm.doc.contribution_file) {
			frm.add_custom_button(
				__("Download Contribution File"),
				() => window.open(frm.doc.contribution_file),
				__("View")
			);
		}
	},
});
