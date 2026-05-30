// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

const MAX_MEMBERS = 12;

frappe.ui.form.on("Grievance Redressal Committee", {
	refresh(frm) {
		const members = frm.doc.members || [];
		const women = members.filter((m) => (m.gender || "").toLowerCase() === "female" && m.is_active).length;
		if (members.length) {
			frm.dashboard.add_indicator(
				__("Members: {0}/{1} · Women: {2}", [members.length, MAX_MEMBERS, women]),
				women >= 1 && members.length <= MAX_MEMBERS ? "green" : "orange",
			);
		}
	},
	validate(frm) {
		const members = frm.doc.members || [];
		if (members.length > MAX_MEMBERS) {
			frappe.throw(__("A GRC may have at most {0} members per IR Code §4.", [MAX_MEMBERS]));
		}
		const women = members.filter((m) => (m.gender || "").toLowerCase() === "female" && m.is_active).length;
		if (frm.doc.status === "Active" && women < 1) {
			frappe.show_alert({
				message: __("At least one woman member is required — IR Code §4(2)."),
				indicator: "orange",
			});
		}
	},
});
