// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("TDS Return Form 24Q", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.company || !frm.doc.fiscal_year || !frm.doc.quarter) return;

		frm.add_custom_button(__("Generate TDS Challan"), () => {
			frappe.call({
				method: "indian_hrms_compliance.payroll.doctype.tds_challan.tds_challan.generate_tds_challan",
				args: { company: frm.doc.company, fiscal_year: frm.doc.fiscal_year, quarter: frm.doc.quarter },
				freeze: true,
				freeze_message: __("Rolling up quarterly TDS…"),
				callback: (r) => {
					if (!r.message) return;
					frappe.show_alert({
						message: __("Challan {0} created (TDS {1})", [r.message.name, format_currency(r.message.tds_amount, "INR")]),
						indicator: "green",
					});
					frappe.set_route("Form", "TDS Challan", r.message.name);
				},
			});
		}, __("Create"));
	},
});
