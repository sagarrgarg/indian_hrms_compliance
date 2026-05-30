// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// Phase 6B-1 — PF ECR Filing form add-ons.
//
//   - "Generate ECR" button on Draft → calls
//     pf_ecr_generator.generate_pf_ecr, then reloads to show rows + file.
//   - "Mark as Filed" button on Generated → prompts for challan number,
//     calls pf_ecr_generator.mark_pf_ecr_filed.
//   - "Download ECR File" quick link when ecr_file is attached.

frappe.ui.form.on("PF ECR Filing", {
	refresh(frm) {
		frm.disable_save();  // status changes only via the buttons below.
		if (!frm.is_new()) {
			frm.enable_save();
		}

		if (frm.is_new()) return;

		// Generate ECR — only on Draft (or re-generate on Generated for fix-ups).
		if (frm.doc.filing_status === "Draft" || frm.doc.filing_status === "Generated") {
			const label = frm.doc.filing_status === "Generated" ? __("Regenerate ECR") : __("Generate ECR");
			frm.add_custom_button(
				label,
				() => {
					frappe.confirm(
						frm.doc.filing_status === "Generated"
							? __("This will overwrite existing rows + the attached ECR file. Continue?")
							: __("Generate the ECR from submitted Salary Slips for this wage month?"),
						() => {
							frappe.call({
								method: "indian_hrms_compliance.overrides.pf_ecr_generator.generate_pf_ecr",
								args: { pf_ecr_filing_name: frm.doc.name },
								freeze: true,
								freeze_message: __("Generating ECR..."),
								callback: (r) => {
									if (r.message) {
										frappe.show_alert({
											message: __("ECR generated: {0} member(s), challan ₹{1}.", [
												r.message.total_members,
												format_currency(r.message.total_remittance),
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

		// Mark as Filed — only on Generated.
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
								description: __("Enter the EPFO challan number after payment."),
							},
						],
						(values) => {
							frappe.call({
								method: "indian_hrms_compliance.overrides.pf_ecr_generator.mark_pf_ecr_filed",
								args: {
									pf_ecr_filing_name: frm.doc.name,
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
						__("Mark PF ECR as Filed"),
						__("Confirm")
					);
				},
				__("Phase 6B")
			);
		}

		// Quick download link.
		if (frm.doc.ecr_file) {
			frm.add_custom_button(
				__("Download ECR File"),
				() => window.open(frm.doc.ecr_file),
				__("View")
			);
		}
	},
});
