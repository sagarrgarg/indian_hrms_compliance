// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

frappe.query_reports["Employees on Probation"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		// Highlight the end date + weeks-left when the confirmation decision is
		// overdue (red) or coming up within DUE_SOON_DAYS (orange). _overdue and
		// _due_soon are computed per row on the Python side.
		const flag = ["probation_end", "weeks_remaining"].includes(column.fieldname);
		if (flag && data._overdue) {
			value = `<span style="background-color:var(--bg-red);color:var(--text-on-red);padding:2px 8px;border-radius:4px;font-weight:500">${value}</span>`;
		} else if (flag && data._due_soon) {
			value = `<span style="background-color:var(--bg-orange);color:var(--text-on-orange);padding:2px 8px;border-radius:4px;font-weight:500">${value}</span>`;
		}
		return value;
	},
};
