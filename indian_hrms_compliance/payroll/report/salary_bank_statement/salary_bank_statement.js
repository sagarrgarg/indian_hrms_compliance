// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt
/* eslint-disable */

// Derive the period end (and snap the start) from the chosen payroll frequency +
// start date — same logic Payroll Entry / Salary Register use (get_start_end_dates).
// Guarded so the programmatic set_filter_value calls don't recurse through on_change.
let _sbs_deriving = false;
function sbs_set_period_dates() {
	if (_sbs_deriving) return;
	const frequency = frappe.query_report.get_filter_value("payroll_frequency");
	const start_date = frappe.query_report.get_filter_value("from_date");
	const company = frappe.query_report.get_filter_value("company");
	if (!frequency || !start_date) return;
	frappe.call({
		method: "indian_hrms_compliance.payroll.doctype.payroll_entry.payroll_entry.get_start_end_dates",
		args: { payroll_frequency: frequency, start_date: start_date, company: company },
		callback: function (r) {
			if (!r.message) return;
			_sbs_deriving = true;
			frappe.query_report.set_filter_value("from_date", r.message.start_date);
			frappe.query_report.set_filter_value("to_date", r.message.end_date);
			_sbs_deriving = false;
		},
	});
}

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
			fieldname: "payroll_frequency",
			label: __("Payroll Frequency"),
			fieldtype: "Select",
			options: ["Monthly", "Fortnightly", "Weekly", "Bimonthly", "Daily"],
			default: "Monthly",
			reqd: 1,
			on_change: function () {
				sbs_set_period_dates();
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
			on_change: function () {
				sbs_set_period_dates();
			},
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
		{
			fieldname: "bank",
			label: __("Bank (only this)"),
			fieldtype: "Link",
			options: "Bank",
		},
		{
			fieldname: "exclude_bank",
			label: __("Exclude Bank"),
			fieldtype: "Link",
			options: "Bank",
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
				bank: f.bank || "",
				exclude_bank: f.exclude_bank || "",
			});
			window.open(
				"/api/method/indian_hrms_compliance.payroll.report.salary_bank_statement.salary_bank_statement.download_salary_bank_statement?" +
					params.toString(),
			);
		});
	},
};
