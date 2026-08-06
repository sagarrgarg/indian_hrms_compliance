// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt
/* eslint-disable */

frappe.query_reports["Salary Bank Statement"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
		{
			fieldname: "use_father_husband_name",
			label: __("Use Father/Husband Name (instead of Designation)"),
			fieldtype: "Check",
		},
	],

	onload: function (report) {
		// Download the exact firm bank-statement workbook (company header + total).
		report.page.add_inner_button(__("Download Bank Format (Excel)"), function () {
			const f = report.get_values();
			if (!f.company) {
				frappe.msgprint(__("Select a Company first."));
				return;
			}
			const params = new URLSearchParams({
				company: f.company,
				from_date: f.from_date || "",
				to_date: f.to_date || "",
				use_father_husband_name: f.use_father_husband_name ? 1 : 0,
			});
			window.open(
				"/api/method/indian_hrms_compliance.payroll.report.salary_bank_statement.salary_bank_statement.download_salary_bank_statement?" +
					params.toString(),
			);
		});
	},
};
