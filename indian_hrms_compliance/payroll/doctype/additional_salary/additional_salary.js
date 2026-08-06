// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Additional Salary", {
	setup: function (frm) {
		frm.add_fetch(
			"salary_component",
			"deduct_full_tax_on_selected_payroll_date",
			"deduct_full_tax_on_selected_payroll_date",
		);

		frm.set_query("employee", function () {
			return {
				filters: {
					company: frm.doc.company,
					status: ["!=", "Inactive"],
					is_virtual_employee: 0,
				},
			};
		});
	},

	onload: function (frm) {
		frm.trigger("set_component_query");
	},

	refresh: function (frm) {
		frm.trigger("toggle_grant_mode");
		frm.trigger("render_approval_actions");
	},

	// Wire the grant approval workflow (backend: submit_for_approval /
	// approve_additional_salary / reject_additional_salary) into the Desk form.
	// Grants born from another document (ref_doctype: advance recovery, legacy
	// wrappers) are auto-approved and need no buttons.
	render_approval_actions: function (frm) {
		if (frm.is_new() || frm.doc.docstatus !== 0 || frm.doc.ref_doctype) return;

		const status = frm.doc.approval_status;
		const call = (method, args) =>
			frappe.call({
				method: `indian_hrms_compliance.payroll.doctype.additional_salary.additional_salary.${method}`,
				args: Object.assign({ name: frm.doc.name }, args || {}),
				freeze: true,
				callback: () => frm.reload_doc(),
			});

		if (status === "Draft" || status === "Rejected") {
			frm.add_custom_button(__("Send for Approval"), () => call("submit_for_approval")).addClass(
				"btn-primary",
			);
		}

		// Only the resolved approver, HR, or a System Manager can decide.
		const roles = frappe.user_roles || [];
		const can_decide =
			roles.includes("System Manager") ||
			roles.includes("HR Manager") ||
			roles.includes("HR User") ||
			frm.doc.approver === frappe.session.user;

		if (status === "Pending Approval" && can_decide) {
			frm.add_custom_button(__("Approve"), () => {
				frappe.confirm(__("Approve this grant? It will be submitted and feed payroll."), () =>
					call("approve_additional_salary"),
				);
			}).addClass("btn-success");

			frm.add_custom_button(__("Reject"), () => {
				frappe.prompt(
					[
						{
							fieldname: "reason",
							fieldtype: "Small Text",
							label: __("Reason for rejection"),
							reqd: 1,
						},
					],
					(v) => call("reject_additional_salary", { reason: v.reason }),
					__("Reject Grant"),
					__("Reject"),
				);
			}).addClass("btn-danger");
		}
	},

	grace_days: function (frm) {
		frm.trigger("toggle_grant_mode");
	},

	// One record grants EITHER a component amount OR Grace Days (a full-day
	// increment). Hide the component/amount pair once Grace Days is entered so the
	// two modes don't get mixed (the server enforces this too).
	toggle_grant_mode: function (frm) {
		const days_only = flt(frm.doc.grace_days) > 0;
		frm.toggle_display(["salary_component", "amount"], !days_only);
	},

	employee: function (frm) {
		if (frm.doc.employee) {
			frappe.run_serially([
				() => frm.trigger("get_employee_currency"),
				() => frm.trigger("set_company"),
			]);
		} else {
			frm.set_value("company", null);
		}
	},

	set_company: function (frm) {
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Employee",
				fieldname: "company",
				filters: {
					name: frm.doc.employee,
				},
			},
			callback: function (data) {
				if (data.message) {
					frm.set_value("company", data.message.company);
				}
			},
		});
	},

	company: function (frm) {
		frm.trigger("set_component_query");
	},

	set_component_query: function (frm) {
		if (!frm.doc.company) return;

		let filters = {
			company: frm.doc.company,
			disabled: 0,
		};

		frm.set_query("salary_component", function () {
			return {
				filters: filters,
			};
		});
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

	salary_component: function (frm) {
		if (!frm.doc.ref_doctype) {
			frm.trigger("get_salary_component_amount");
		}
	},

	get_salary_component_amount: function (frm) {
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Salary Component",
				fieldname: "amount",
				filters: {
					name: frm.doc.salary_component,
				},
			},
			callback: function (data) {
				if (data.message) {
					frm.set_value("amount", data.message.amount);
				}
			},
		});
	},
});
