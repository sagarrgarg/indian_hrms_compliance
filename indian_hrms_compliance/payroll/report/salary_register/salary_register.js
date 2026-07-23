// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Salary Register"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
			width: "100px",
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
			width: "100px",
		},
		{
			fieldname: "currency",
			fieldtype: "Link",
			options: "Currency",
			label: __("Currency"),
			default: erpnext.get_currency(frappe.defaults.get_default("Company")),
			width: "50px",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
			width: "100px",
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			width: "100px",
			reqd: 1,
		},
		{
			fieldname: "docstatus",
			label: __("Document Status"),
			fieldtype: "Select",
			options: ["Draft", "Submitted", "Cancelled"],
			default: "Submitted",
			width: "100px",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
			width: "100px",
			get_query: function () {
				return {
					filters: {
						company: frappe.query_report.get_filter_value("company"),
					},
				};
			},
		},
		{
			fieldname: "designation",
			label: __("Designation"),
			fieldtype: "Link",
			options: "Designation",
			width: "100px",
		},
		{
			fieldname: "branch",
			label: __("Branch"),
			fieldtype: "Link",
			options: "Branch",
			width: "100px",
		},
	],

	onload: function (report) {
		const open_pdf = (method, busy) => {
			const filters = report.get_values();
			if (!filters.company) {
				frappe.msgprint(__("Please select a Company."));
				return;
			}
			frappe.dom.freeze(busy);
			frappe
				.call({
					method:
						"indian_hrms_compliance.payroll.report.salary_register.salary_register." +
						method,
					args: { filters: filters },
				})
				.then((r) => {
					frappe.dom.unfreeze();
					if (r.message) {
						const w = window.open("", "_blank");
						w.document.write(r.message);
						w.document.close();
					}
				})
				.catch(() => frappe.dom.unfreeze());
		};

		report.page.add_inner_button(__("Wages Register (PDF)"), function () {
			open_pdf("get_wages_register_html", __("Building Wages Register…"));
		});
		report.page.add_inner_button(__("Grand Total Summary (PDF)"), function () {
			open_pdf("get_payroll_summary_html", __("Building Payroll Summary…"));
		});
	},
};
