// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt
/* eslint-disable */

frappe.query_reports["Time and Overtime Register"] = {
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
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "weekly_breakdown",
			label: __("Weekly breakdown (one row per week)"),
			fieldtype: "Check",
		},
	],

	onload(report) {
		if (!frappe.user.has_role(["HR Manager", "System Manager"])) return;
		report.page.add_inner_button(__("Create Overtime Pay"), () => {
			const f = report.get_values();
			if (!f) return;
			frappe.prompt(
				[
					{
						fieldname: "payroll_date",
						label: __("Payroll Date"),
						fieldtype: "Date",
						default: f.to_date,
						reqd: 1,
					},
					{
						fieldname: "submit",
						label: __("Approve and submit now (otherwise drafts for approval)"),
						fieldtype: "Check",
					},
				],
				(v) => {
					frappe.call({
						method: "indian_hrms_compliance.payroll.overtime.create_overtime_pay",
						args: {
							company: f.company,
							from_date: f.from_date,
							to_date: f.to_date,
							payroll_date: v.payroll_date,
							submit: v.submit,
						},
						freeze: true,
						callback: (r) => {
							const s = r.message || {};
							let msg = __("Created {0}, updated {1} overtime Additional Salaries.", [
								(s.created || []).length,
								(s.updated || []).length,
							]);
							if ((s.skipped || []).length) {
								msg += "<br><br>" + __("Skipped:") + "<br>" + s.skipped.join("<br>");
							}
							if ((s.over_quarterly_limit || []).length) {
								msg +=
									"<br><br>" +
									__("Above the {0}-hour quarterly limit:", [s.quarterly_limit]) +
									"<br>" +
									s.over_quarterly_limit
										.map((o) => `${o.employee}: ${o.quarter_hours} h`)
										.join("<br>");
							}
							frappe.msgprint({ title: __("Overtime Pay"), message: msg });
						},
					});
				},
				__("Create Overtime Pay"),
				__("Create")
			);
		});
	},
};
