// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

frappe.ui.form.on("New Employee Setup", {
	refresh: function (frm) {
		frm.trigger("set_filters");

		if (frm.is_new()) return;

		if (frm.doc.created_employee) {
			frm.add_custom_button(
				__("Open Employee"),
				() => frappe.set_route("Form", "Employee", frm.doc.created_employee),
				__("View"),
			);
			if (frm.doc.created_user) {
				frm.add_custom_button(
					__("Open User"),
					() => frappe.set_route("Form", "User", frm.doc.created_user),
					__("View"),
				);
			}
			return;
		}

		frm.add_custom_button(__("Create Employee"), function () {
			frappe.confirm(
				__("Create the Employee, User login and linked records now?"),
				function () {
					frm.call({
						method: "create_employee_and_setup",
						doc: frm.doc,
						freeze: true,
						freeze_message: __("Setting up the new employee…"),
						callback: function (r) {
							if (!r.message) return;
							frappe.msgprint({
								title: __("Employee Created"),
								indicator: "green",
								message: (r.message.log || []).join("<br>"),
							});
							frm.reload_doc();
						},
					});
				},
			);
		}).addClass("btn-primary");
	},

	set_filters: function (frm) {
		// Reporting manager: Active employees of the same company.
		frm.set_query("reports_to", () => ({
			filters: { company: frm.doc.company, status: "Active" },
		}));

		// Approvers: Active, same company, and must have a linked User.
		["leave_approver", "expense_approver", "shift_request_approver"].forEach((field) => {
			frm.set_query(field, () => ({
				filters: { company: frm.doc.company, status: "Active", user_id: ["is", "set"] },
			}));
		});

		frm.set_query("salary_structure", () => ({
			filters: { company: frm.doc.company, docstatus: 1, is_active: "Yes" },
		}));

		frm.set_query("department", () => ({ filters: { company: frm.doc.company } }));
	},

	company: function (frm) {
		frm.trigger("set_filters");
	},

	date_of_joining: function (frm) {
		if (frm.doc.date_of_joining && !frm.doc.payroll_effective_date) {
			frm.set_value("payroll_effective_date", frm.doc.date_of_joining);
		}
	},
});
