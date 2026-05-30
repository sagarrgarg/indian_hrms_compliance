// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

frappe.ui.form.on("Resignation Request", {
	refresh(frm) {
		if (frm.doc.linked_employee_separation) {
			frm.add_custom_button(
				__("Open Separation"),
				() => frappe.set_route("Form", "Employee Separation", frm.doc.linked_employee_separation),
				__("View")
			);
		}
		if (frm.doc.linked_full_and_final) {
			frm.add_custom_button(
				__("Open Full and Final"),
				() => frappe.set_route("Form", "Full and Final Statement", frm.doc.linked_full_and_final),
				__("View")
			);
		}
	},

	notice_offered_days(frm) {
		_recompute_intended_last_working_date(frm);
	},
	submission_date(frm) {
		_recompute_intended_last_working_date(frm);
	},
	request_type(frm) {
		// Derive initiated_by on the client too so the user sees it immediately.
		frm.set_value("initiated_by", frm.doc.request_type === "Resignation" ? "Employee" : "Employer");
	},
});

function _recompute_intended_last_working_date(frm) {
	if (!frm.doc.submission_date || frm.doc.notice_offered_days == null) return;
	const d = frappe.datetime.add_days(frm.doc.submission_date, frm.doc.notice_offered_days);
	frm.set_value("intended_last_working_date", d);
}
