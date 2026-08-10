// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["PF Contribution Register"] = {
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
			fieldname: "wage_month",
			label: __("Wage Month"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
			description: __("Any date in the wage month you want the register for."),
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "filing_status",
			label: __("Filing Status"),
			fieldtype: "Select",
			options: ["", "Draft", "Generated", "Filed"].join("\n"),
		},
	],
};
