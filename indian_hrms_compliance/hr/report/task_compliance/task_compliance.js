// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

frappe.query_reports["Task Compliance"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
			reqd: 0,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 0,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "kra",
			label: __("KRA"),
			fieldtype: "Link",
			options: "KRA",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "compliance_pct" && data) {
			// Thresholds come from HR Settings — surfaced on each row by the
			// Python side as _warn_pct / _crit_pct. >= warn = green,
			// >= crit = orange, < crit = red. Defaults match HR Settings defaults.
			const warn = data._warn_pct != null ? data._warn_pct : 80;
			const crit = data._crit_pct != null ? data._crit_pct : 50;
			let color = "var(--text-on-red)";
			let bg = "var(--bg-red)";
			if (data.compliance_pct >= warn) {
				color = "var(--text-on-green)";
				bg = "var(--bg-green)";
			} else if (data.compliance_pct >= crit) {
				color = "var(--text-on-orange)";
				bg = "var(--bg-orange)";
			}
			value = `<span style="background-color:${bg};color:${color};padding:2px 8px;border-radius:4px;font-weight:500">${value}</span>`;
		}
		if (column.fieldname === "overdue" && data && data.overdue > 0) {
			value = `<span style="color:#c0392b;font-weight:500">${value}</span>`;
		}
		return value;
	},
};
