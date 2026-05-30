// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// Phase 6C — Compliance Return Definition form add-ons.
//
//   - "Auto-populate Filings for FY" — calls
//     overrides.compliance_calendar.populate_compliance_filings_for_period
//     for the current FY of the doc's Company.

frappe.ui.form.on("Compliance Return Definition", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (!frm.doc.applicable) return;

		frm.add_custom_button(
			__("Auto-populate Filings for FY"),
			() => {
				// Compute Indian FY containing today.
				const today = frappe.datetime.get_today();
				const td = frappe.datetime.str_to_obj(today);
				const year = td.getMonth() >= 3 ? td.getFullYear() : td.getFullYear() - 1;
				const fy_start = `${year}-04-01`;
				const fy_end = `${year + 1}-03-31`;

				frappe.prompt(
					[
						{
							label: __("From Date"),
							fieldname: "from_date",
							fieldtype: "Date",
							default: fy_start,
							reqd: 1,
						},
						{
							label: __("To Date"),
							fieldname: "to_date",
							fieldtype: "Date",
							default: fy_end,
							reqd: 1,
						},
					],
					(values) => {
						frappe.call({
							method: "indian_hrms_compliance.overrides.compliance_calendar.populate_compliance_filings_for_period",
							args: {
								company: frm.doc.company,
								from_date: values.from_date,
								to_date: values.to_date,
							},
							freeze: true,
							freeze_message: __("Populating Compliance Filings..."),
							callback: (r) => {
								if (r.message) {
									frappe.msgprint({
										title: __("Done"),
										message: __(
											"Created <b>{0}</b> new Compliance Filing row(s). " +
												"Skipped <b>{1}</b> existing.",
											[r.message.created_count, r.message.skipped_existing]
										),
										indicator: "green",
									});
								}
							},
						});
					},
					__("Auto-populate Compliance Filings"),
					__("Generate")
				);
			},
			__("Phase 6C")
		);
	},
});
