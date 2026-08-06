// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

// Derive the period end (and snap the start) from the chosen payroll frequency +
// start date — same logic Payroll Entry uses (get_start_end_dates). Guarded so the
// programmatic set_filter_value calls don't recurse through on_change.
let _sr_deriving = false;
function sr_set_period_dates() {
	if (_sr_deriving) return;
	const frequency = frappe.query_report.get_filter_value("payroll_frequency");
	const start_date = frappe.query_report.get_filter_value("from_date");
	const company = frappe.query_report.get_filter_value("company");
	if (!frequency || !start_date) return;
	frappe.call({
		method: "indian_hrms_compliance.payroll.doctype.payroll_entry.payroll_entry.get_start_end_dates",
		args: { payroll_frequency: frequency, start_date: start_date, company: company },
		callback: function (r) {
			if (!r.message) return;
			_sr_deriving = true;
			frappe.query_report.set_filter_value("from_date", r.message.start_date);
			frappe.query_report.set_filter_value("to_date", r.message.end_date);
			_sr_deriving = false;
		},
	});
}

frappe.query_reports["Salary Register"] = {
	filters: [
		{
			fieldname: "payroll_frequency",
			label: __("Payroll Frequency"),
			fieldtype: "Select",
			options: ["Monthly", "Fortnightly", "Weekly", "Bimonthly", "Daily"],
			default: "Monthly",
			reqd: 1,
			width: "100px",
			on_change: function () {
				sr_set_period_dates();
			},
		},
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
			width: "100px",
			on_change: function () {
				sr_set_period_dates();
			},
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
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
