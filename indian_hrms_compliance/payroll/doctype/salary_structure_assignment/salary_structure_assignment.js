// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Salary Structure Assignment", {
	setup: function (frm) {
		frm.set_query("employee", function () {
			return {
				query: "erpnext.controllers.queries.employee_query",
				filters: { company: frm.doc.company },
			};
		});
		frm.set_query("salary_structure", function () {
			return {
				filters: {
					company: frm.doc.company,
					docstatus: 1,
					is_active: "Yes",
				},
			};
		});

		frm.set_query("income_tax_slab", function () {
			return { filters: { docstatus: 1 } };
		});

		frm.set_query("payroll_payable_account", function () {
			var company_currency = erpnext.get_currency(frm.doc.company);
			return {
				filters: {
					company: frm.doc.company,
					root_type: "Liability",
					is_group: 0,
					account_currency: ["in", [frm.doc.currency, company_currency]],
				},
			};
		});

		frm.set_query("cost_center", "payroll_cost_centers", function () {
			return {
				filters: {
					company: frm.doc.company,
					is_group: 0,
				},
			};
		});
	},

	refresh: function (frm) {
		frm.trigger("toggle_opening_balances_section");

		// Available pre-save: tweak base / variable / leave encashment and see
		// the formula-computed payslip.
		frm.add_custom_button(
			__("Preview Salary"),
			() => frm.trigger("open_salary_preview"),
			__("Actions"),
		);

		if (frm.doc.docstatus != 1) return;

		frm.add_custom_button(
			__("Payroll Entry"),
			() => {
				frappe.model.with_doctype("Payroll Entry", () => {
					const doc = frappe.model.get_new_doc("Payroll Entry");
					frappe.set_route("Form", "Payroll Entry", doc.name);
				});
			},
			__("Create"),
		);
		frm.page.set_inner_btn_group_as_primary(__("Create"));

		frm.add_custom_button(
			__("Preview Salary Slip"),
			function () {
				frm.trigger("preview_salary_slip");
			},
			__("Actions"),
		);
	},

	employee: function (frm) {
		if (frm.doc.employee) {
			frm.trigger("set_payroll_cost_centers");
			frm.trigger("toggle_opening_balances_section");
		} else {
			frm.set_value("payroll_cost_centers", []);
		}
	},

	company: function (frm) {
		if (frm.doc.company) {
			frappe.db.get_value(
				"Company",
				frm.doc.company,
				"default_payroll_payable_account",
				(r) => {
					frm.set_value("payroll_payable_account", r.default_payroll_payable_account);
				},
			);
		}
	},

	preview_salary_slip: function (frm) {
		frappe.db.get_value(
			"Salary Structure",
			frm.doc.salary_structure,
			"salary_slip_based_on_timesheet",
			(r) => {
				const print_format = r.salary_slip_based_on_timesheet
					? "Salary Slip based on Timesheet"
					: "Salary Slip Standard";
				frappe.call({
					method: "indian_hrms_compliance.payroll.doctype.salary_structure.salary_structure.make_salary_slip",
					args: {
						source_name: frm.doc.salary_structure,
						employee: frm.doc.employee,
						posting_date: frm.doc.from_date,
						as_print: 1,
						print_format: print_format,
						for_preview: 1,
					},
					callback: function (r) {
						const new_window = window.open();
						new_window.document.write(r.message);
					},
				});
			},
		);
	},

	open_salary_preview: function (frm) {
		if (!frm.doc.salary_structure) {
			frappe.msgprint(__("Please select a Salary Structure first."));
			return;
		}
		const fmt = (v) => format_currency(v, frm.doc.currency);
		const dialog = new frappe.ui.Dialog({
			title: __("Salary Preview"),
			fields: [
				{ fieldname: "base", fieldtype: "Currency", label: __("Base"), default: frm.doc.base || 0 },
				{ fieldname: "variable", fieldtype: "Currency", label: __("Variable"), default: frm.doc.variable || 0 },
				{ fieldname: "cb", fieldtype: "Column Break" },
				{ fieldname: "leave_encashment", fieldtype: "Currency", label: __("Leave Encashment"), default: 0 },
				{
					fieldname: "income_tax_slab",
					fieldtype: "Link",
					options: "Income Tax Slab",
					label: __("Income Tax Slab"),
					default: frm.doc.income_tax_slab,
				},
				{ fieldname: "sb", fieldtype: "Section Break" },
				{ fieldname: "results", fieldtype: "HTML" },
			],
			primary_action_label: __("Compute"),
			primary_action(values) {
				frappe.call({
					method: "indian_hrms_compliance.payroll.doctype.salary_structure_assignment.salary_structure_assignment.preview_salary",
					args: {
						salary_structure: frm.doc.salary_structure,
						base: values.base || 0,
						variable: values.variable || 0,
						leave_encashment: values.leave_encashment || 0,
						employee: frm.doc.employee,
						income_tax_slab: frm.doc.income_tax_slab,
					},
					freeze: true,
					callback: function (r) {
						const m = r.message;
						if (!m) return;
						const row = (label, amt, note) =>
							`<tr><td style="padding:3px 8px;">${frappe.utils.escape_html(label)}${
								note ? ` <span style="color:#999;font-size:11px;">(${note})</span>` : ""
							}</td><td style="padding:3px 8px;text-align:right;">${fmt(amt)}</td></tr>`;
						let html = `<div style="display:flex;gap:16px;flex-wrap:wrap;">`;
						html += `<div style="flex:1;min-width:220px;"><div style="font-weight:600;color:#1f8c4d;margin-bottom:4px;">${__(
							"Earnings",
						)}</div><table style="width:100%;border-collapse:collapse;">${m.earnings
							.map((e) => row(e.component + (e.statistical ? " *" : ""), e.amount))
							.join("")}</table></div>`;
						html += `<div style="flex:1;min-width:220px;"><div style="font-weight:600;color:#c0392b;margin-bottom:4px;">${__(
							"Deductions",
						)}</div><table style="width:100%;border-collapse:collapse;">${m.deductions
							.map((d) => row(d.component, d.amount, d.note))
							.join("")}</table></div>`;
						html += `</div><hr>`;
						html += `<table style="width:100%;border-collapse:collapse;font-weight:600;">
							${row(__("Gross Pay"), m.gross)}
							${row(__("Total Deductions"), m.total_deduction)}
							<tr><td style="padding:6px 8px;font-size:15px;">${__("Net Pay")}</td><td style="padding:6px 8px;text-align:right;font-size:15px;color:#1f8c4d;">${fmt(
								m.net,
							)}</td></tr></table>
							<div style="color:#999;font-size:11px;margin-top:6px;">* ${__("statistical / CTC component, not paid in net")}</div>`;
						if (m.tax) {
							const t = m.tax;
							html += `<hr><div style="font-weight:600;margin-bottom:4px;">${__(
								"Income Tax (estimate)",
							)}</div><table style="width:100%;border-collapse:collapse;">
								${row(__("Annual Gross"), t.annual_gross)}
								${row(__("Standard Deduction"), -t.standard_deduction)}
								${row(__("Taxable Income"), t.taxable_income)}
								${
									t.rebate_applied
										? `<tr><td colspan="2" style="padding:3px 8px;color:#1f8c4d;">${__(
												"Within 87A rebate (up to {0}) — nil tax",
												[format_currency(t.relief_limit, frm.doc.currency)],
											)}</td></tr>`
										: (t.marginal_relief
												? row(__("Tax (after marginal relief)"), t.annual_tax)
												: row(__("Annual Tax"), t.annual_tax)) + row(__("Cess"), t.cess)
								}
								${row(__("Annual Tax + Cess"), t.annual_total)}
								${row(__("Monthly TDS"), t.monthly_tds)}
							</table>
							<div style="color:#999;font-size:11px;margin-top:6px;">${__(
								"Estimate — excludes surcharge & Chapter VI-A.",
							)}</div>`;
						}
						dialog.fields_dict.results.$wrapper.html(html);
					},
				});
			},
		});
		dialog.show();
	},

	set_payroll_cost_centers: function (frm) {
		if (frm.doc.payroll_cost_centers && frm.doc.payroll_cost_centers.length < 1) {
			frappe.call({
				method: "set_payroll_cost_centers",
				doc: frm.doc,
				callback: function (data) {
					refresh_field("payroll_cost_centers");
				},
			});
		}
	},

	toggle_opening_balances_section: function (frm) {
		if (!frm.doc.from_date || !frm.doc.employee || !frm.doc.salary_structure) return;

		frm.call("are_opening_entries_required").then((data) => {
			if (data.message) {
				frm.set_df_property("opening_balances_section", "hidden", 0);
			} else {
				frm.set_df_property("opening_balances_section", "hidden", 1);
			}
		});
	},

	from_date: function (frm) {
		if (frm.doc.from_date) {
			frm.trigger("toggle_opening_balances_section");
		}
	},
});
