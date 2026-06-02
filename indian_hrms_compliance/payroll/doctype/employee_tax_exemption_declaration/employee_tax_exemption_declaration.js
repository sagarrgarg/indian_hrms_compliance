// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Tax Exemption Declaration", {
	setup: function (frm) {
		frm.set_query("employee", function () {
			return {
				filters: {
					status: "Active",
				},
			};
		});

		// Payroll Periods are national (company-blank) by default, so do NOT
		// filter by company here — that would hide the national period and leave
		// nothing to select. All periods are selectable.
		frm.set_query("exemption_sub_category", "declarations", function () {
			return {
				filters: {
					is_active: 1,
				},
			};
		});
	},

	refresh: function (frm) {
		if (frm.doc.docstatus == 1) {
			frm.add_custom_button(__("Submit Proof"), function () {
				frappe.model.open_mapped_doc({
					method: "indian_hrms_compliance.payroll.doctype.employee_tax_exemption_declaration.employee_tax_exemption_declaration.make_proof_submission",
					frm: frm,
				});
			}).addClass("btn-primary");
		}
	},

	employee: function (frm) {
		if (frm.doc.employee) {
			frm.trigger("get_employee_currency");
		}
	},

	get_employee_currency: function (frm) {
		frappe.call({
			method: "indian_hrms_compliance.payroll.doctype.salary_structure_assignment.salary_structure_assignment.get_employee_currency",
			args: {
				employee: frm.doc.employee,
			},
			callback: function (r) {
				if (r.message) {
					frm.set_value("currency", r.message);
					frm.refresh_fields();
				}
			},
		});
	},
});
