// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// Phase 6C — Compliance Filing form add-ons.
//
//   - Indicator banner when overdue.
//   - "Open Linked Filing" button when linked_filing_doctype + linked_filing_name set.
//   - "Mark as Filed" prompts for ack_number + filed_on, calls mark_as_filed.
//   - "Waive" prompts for reason, calls waive.

frappe.ui.form.on("Compliance Filing", {
	refresh(frm) {
		if (frm.is_new()) return;

		// Overdue indicator banner.
		const today = frappe.datetime.get_today();
		const is_overdue =
			frm.doc.due_date &&
			frappe.datetime.str_to_obj(frm.doc.due_date) < frappe.datetime.str_to_obj(today) &&
			!["Filed", "Late Filed", "Waived", "Not Applicable"].includes(frm.doc.filing_status);

		if (is_overdue) {
			frm.dashboard.set_headline(
				`<span style="color:#c0392b"><strong>OVERDUE</strong> — was due ${frappe.datetime.str_to_user(
					frm.doc.due_date
				)}. Late filing may attract penalty.</span>`
			);
		}

		// Open Linked Filing.
		if (frm.doc.linked_filing_doctype && frm.doc.linked_filing_name) {
			frm.add_custom_button(
				__("Open Linked Filing"),
				() => {
					frappe.set_route(
						"Form",
						frm.doc.linked_filing_doctype,
						frm.doc.linked_filing_name
					);
				},
				__("Phase 6C")
			);
		}

		// Mark as Filed — only when not already filed / waived.
		if (
			!["Filed", "Late Filed", "Waived", "Not Applicable"].includes(
				frm.doc.filing_status
			)
		) {
			frm.add_custom_button(
				__("Mark as Filed"),
				() => {
					frappe.prompt(
						[
							{
								label: __("Acknowledgement Number"),
								fieldname: "acknowledgement_number",
								fieldtype: "Data",
								reqd: 0,
							},
							{
								label: __("Filed On"),
								fieldname: "filed_on",
								fieldtype: "Date",
								default: frappe.datetime.get_today(),
								reqd: 1,
							},
							{
								label: __("Amount Filed"),
								fieldname: "amount_filed",
								fieldtype: "Currency",
								default: frm.doc.amount_filed || 0,
							},
						],
						(values) => {
							frappe.call({
								method: "indian_hrms_compliance.hr.doctype.compliance_filing.compliance_filing.mark_as_filed",
								args: {
									name: frm.doc.name,
									acknowledgement_number: values.acknowledgement_number || "",
									filed_on: values.filed_on,
									amount_filed: values.amount_filed || 0,
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
						__("Mark Compliance Filing as Filed"),
						__("Confirm")
					);
				},
				__("Phase 6C")
			);

			// Waive button.
			frm.add_custom_button(
				__("Waive"),
				() => {
					frappe.prompt(
						[
							{
								label: __("Reason"),
								fieldname: "reason",
								fieldtype: "Small Text",
								reqd: 1,
							},
						],
						(values) => {
							frappe.call({
								method: "indian_hrms_compliance.hr.doctype.compliance_filing.compliance_filing.waive",
								args: { name: frm.doc.name, reason: values.reason },
								freeze: true,
								callback: () => {
									frappe.show_alert({
										message: __("Waived."),
										indicator: "orange",
									});
									frm.reload_doc();
								},
							});
						},
						__("Waive Compliance Filing"),
						__("Confirm")
					);
				},
				__("Phase 6C")
			);
		}
	},
});
