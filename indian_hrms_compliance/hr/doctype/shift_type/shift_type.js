// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Shift Type", {
	refresh: function (frm) {
		if (frm.doc.__islocal) return;

		indian_hrms_compliance.add_shift_tools_button_to_form(frm, {
			action: "Assign Shift",
			shift_type: frm.doc.name,
		});

		frm.add_custom_button(__("Mark Attendance"), () => {
			if (!frm.doc.enable_auto_attendance) {
				frm.scroll_to_field("enable_auto_attendance");
				frappe.throw(__("Please Enable Auto Attendance and complete the setup first."));
			}

			if (!frm.doc.process_attendance_after) {
				frm.scroll_to_field("process_attendance_after");
				frappe.throw(__("Please set {0}.", [__("Process Attendance After").bold()]));
			}

			frm.call({
				doc: frm.doc,
				method: "process_auto_attendance",
				freeze: true,
				args: {
					is_manually_triggered: true,
				},
				callback: (r) => {
					frappe.msgprint(__(r.message));
				},
			});
		});
	},
});
