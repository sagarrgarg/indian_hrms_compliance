// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Gig Platform Worker", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.status === "Active") {
			frm.dashboard.add_indicator(__("Active gig worker"), "green");
		}
		if (frm.doc.ss_scheme_enrolled) {
			frm.dashboard.add_indicator(__("SS Scheme enrolled"), "blue");
		}
		if (!frm.doc.uan) {
			frm.dashboard.add_indicator(__("UAN missing (SS Code §142)"), "orange");
		}
	},
	aadhaar_last_4(frm) {
		if (frm.doc.aadhaar_last_4 && !/^\d{4}$/.test(frm.doc.aadhaar_last_4)) {
			frappe.show_alert({
				message: __("Aadhaar Last 4 must be exactly 4 digits."),
				indicator: "red",
			});
		}
	},
});
