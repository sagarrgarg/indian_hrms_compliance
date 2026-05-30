// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Works Committee", {
	refresh(frm) {
		const workmen = (frm.doc.workmen_representatives || []).length;
		const employer = (frm.doc.employer_representatives || []).length;
		if (workmen || employer) {
			frm.dashboard.add_indicator(
				__("Workmen: {0} · Employer: {1}", [workmen, employer]),
				workmen >= employer ? "green" : "orange",
			);
		}
	},
	validate(frm) {
		const workmen = (frm.doc.workmen_representatives || []).length;
		const employer = (frm.doc.employer_representatives || []).length;
		if (workmen < employer) {
			frappe.show_alert({
				message: __(
					"Workmen reps ({0}) should not be less than employer reps ({1}) — IR Code §3(2).",
					[workmen, employer],
				),
				indicator: "orange",
			});
		}
	},
});
