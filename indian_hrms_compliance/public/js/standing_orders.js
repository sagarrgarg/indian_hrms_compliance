// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Standing Orders", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.status === "Active") {
			frm.dashboard.add_indicator(__("Active under IR Code §28"), "green");
		}
		if (frm.doc.status === "Superseded") {
			frm.dashboard.add_indicator(__("Superseded"), "grey");
		}

		if (!frm.is_new() && frm.doc.status === "Draft") {
			frm.add_custom_button(__("Pre-fill Worker Count"), () => {
				if (!frm.doc.company) {
					frappe.msgprint(__("Set Company first."));
					return;
				}
				frappe.db
					.count("Employee", {
						filters: { company: frm.doc.company, status: "Active" },
					})
					.then((count) => {
						frm.set_value("worker_count_at_filing", count);
						frm.refresh_field("worker_count_at_filing");
					});
			});
		}
	},

	company(frm) {
		if (frm.doc.company && !frm.doc.worker_count_at_filing) {
			frappe.db
				.count("Employee", {
					filters: { company: frm.doc.company, status: "Active" },
				})
				.then((count) => {
					if (count) {
						frm.set_value("worker_count_at_filing", count);
					}
				});
		}
	},
});
