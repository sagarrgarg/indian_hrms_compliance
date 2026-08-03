frappe.provide("indian_hrms_compliance");

$.extend(indian_hrms_compliance, {
	proceed_save_with_reminders_frequency_change: () => {
		frappe.ui.hide_open_dialog();
		frappe.call({
			method: "indian_hrms_compliance.hr.doctype.hr_settings.hr_settings.set_proceed_with_frequency_change",
			callback: () => {
				// nosemgrep: frappe-semgrep-rules.rules.frappe-cur-frm-usage
				cur_frm.save();
			},
		});
	},

	set_payroll_frequency_to_null: (frm) => {
		if (cint(frm.doc.salary_slip_based_on_timesheet)) {
			frm.set_value("payroll_frequency", "");
		}
	},

	get_current_employee: async (frm) => {
		const employee = (
			await frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name")
		)?.message?.name;

		return employee;
	},

	validate_mandatory_fields: (frm, selected_rows, items = "Employees") => {
		const missing_fields = [];
		for (d in frm.fields_dict) {
			if (frm.fields_dict[d].df.reqd && !frm.doc[d] && d !== "__newname")
				missing_fields.push(frm.fields_dict[d].df.label);
		}

		if (missing_fields.length) {
			let message = __("Mandatory fields required for this action:");
			message += "<br><br><ul><li>" + missing_fields.join("</li><li>") + "</ul>";
			frappe.throw({
				message: message,
				title: __("Missing Fields"),
			});
		}

		if (!selected_rows.length)
			frappe.throw({
				message: __("Please select at least one row to perform this action."),
				title: __("No {0} Selected", [__(items)]),
			});
	},

	setup_employee_filter_group: (frm) => {
		const filter_wrapper = frm.fields_dict.filter_list.$wrapper;
		filter_wrapper.empty();

		frappe.model.with_doctype("Employee", () => {
			frm.filter_list = new frappe.ui.FilterGroup({
				parent: filter_wrapper,
				doctype: "Employee",
				on_change: () => {
					frm.advanced_filters = frm.filter_list
						.get_filters()
						.reduce((filters, item) => {
							// item[3] is the value from the array [doctype, fieldname, condition, value]
							if (item[3]) {
								filters.push(item.slice(1, 4));
							}
							return filters;
						}, []);
					frm.trigger("get_employees");
				},
			});
		});
	},

	render_employees_datatable: (
		frm,
		columns,
		employees,
		no_data_message = __("No Data"),
		get_editor = null,
		events = {},
	) => {
		// section automatically collapses on applying a single filter
		frm.set_df_property("quick_filters_section", "collapsible", 0);
		frm.set_df_property("advanced_filters_section", "collapsible", 0);

		if (frm.employees_datatable) {
			frm.employees_datatable.rowmanager.checkMap = [];
			frm.employees_datatable.options.noDataMessage = no_data_message;
			frm.employees_datatable.refresh(employees, columns);
			return;
		}

		const $wrapper = frm.get_field("employees_html").$wrapper;
		const employee_wrapper = $(`<div class="employee_wrapper">`).appendTo($wrapper);
		const datatable_options = {
			columns: columns,
			data: employees,
			checkboxColumn: true,
			checkedRowStatus: false,
			serialNoColumn: false,
			dynamicRowHeight: true,
			inlineFilters: true,
			layout: "fluid",
			cellHeight: 35,
			noDataMessage: no_data_message,
			disableReorderColumn: true,
			getEditor: get_editor,
			events: events,
		};
		frm.employees_datatable = new frappe.DataTable(employee_wrapper.get(0), datatable_options);
	},

	handle_realtime_bulk_action_notification: (frm, event, doctype) => {
		frappe.realtime.off(event);
		frappe.realtime.on(event, (message) => {
			indian_hrms_compliance.notify_bulk_action_status(
				doctype,
				message.failure,
				message.success,
				message.for_processing,
			);

			// refresh only on complete/partial success
			if (message.success) frm.refresh();
		});
	},

	notify_bulk_action_status: (doctype, failure, success, for_processing = false) => {
		let action = __("create/submit");
		let action_past = __("created");
		if (for_processing) {
			action = __("process");
			action_past = __("processed");
		}

		let message = "";
		let title = __("Success");
		let indicator = "green";

		if (failure.length) {
			message += __("Failed to {0} {1} for employees:", [action, doctype]);
			message += " " + frappe.utils.comma_and(failure) + "<hr>";
			message += __(
				"Check <a href='/app/List/Error Log?reference_doctype={0}'>{1}</a> for more details",
				[doctype, __("Error Log")],
			);
			title = __("Failure");
			indicator = "red";

			if (success.length) {
				message += "<hr>";
				title = __("Partial Success");
				indicator = "orange";
			}
		}

		if (success.length) {
			message += __("Successfully {0} {1} for the following employees:", [
				action_past,
				doctype,
			]);
			message += __(
				"<table class='table table-bordered'><tr><th>{0}</th><th>{1}</th></tr>",
				[__("Employee"), doctype],
			);
			for (const d of success) {
				message += `<tr><td>${d.employee}</td><td>${d.doc}</td></tr>`;
			}
			message += "</table>";
		}

		frappe.msgprint({
			message,
			title,
			indicator,
			is_minimizable: true,
		});
	},

	fetch_geolocation: async (frm) => {
		if (!navigator.geolocation) {
			frappe.msgprint({
				message: __("Geolocation is not supported by your current browser"),
				title: __("Geolocation Error"),
				indicator: "red",
			});
			hide_field(["geolocation"]);
			return;
		}

		frappe.dom.freeze(__("Fetching your geolocation") + "...");

		navigator.geolocation.getCurrentPosition(
			async (position) => {
				frappe.run_serially([
					() => frm.set_value("latitude", position.coords.latitude),
					() => frm.set_value("longitude", position.coords.longitude),
					() => frm.call("set_geolocation"),
					() => frappe.dom.unfreeze(),
				]);
			},

			(error) => {
				frappe.dom.unfreeze();

				let msg = __("Unable to retrieve your location") + "<br><br>";
				if (error) {
					msg += __("ERROR({0}): {1}", [error.code, error.message]);
				}
				frappe.msgprint({
					message: msg,
					title: __("Geolocation Error"),
					indicator: "red",
				});
			},
		);
	},

	get_doctype_fields_for_autocompletion: (doctype) => {
		const fields = frappe.get_meta(doctype).fields;
		const autocompletions = [];

		fields
			.filter((df) => !frappe.model.no_value_type.includes(df.fieldtype))
			.map((df) => {
				autocompletions.push({
					value: df.fieldname,
					score: 8,
					meta: __("{0} Field", [doctype]),
				});
			});

		return autocompletions;
	},

	add_shift_tools_button_to_list: (list_view, action = "Assign Shift") => {
		list_view.page.add_inner_button(
			__("Shift Assignment Tool"),
			() => {
				const doc = frappe.model.get_new_doc("Shift Assignment Tool");
				doc.action = action;
				doc.company = frappe.defaults.get_default("company");
				doc.status = "Active";
				frappe.set_route("Form", "Shift Assignment Tool", doc.name);
			},
			__("Shift Tools"),
		);

		list_view.page.add_inner_button(
			__("Roster"),
			() => {
				window.location.href = "/hr/roster";
			},
			__("Shift Tools"),
		);
	},

	add_shift_tools_button_to_form: (frm, fields) => {
		frm.add_custom_button(
			__("Shift Assignment Tool"),
			() => {
				const doc = frappe.model.get_new_doc("Shift Assignment Tool");
				Object.assign(doc, fields);
				doc.company = frappe.defaults.get_default("company");
				doc.status = "Active";
				frappe.set_route("Form", "Shift Assignment Tool", doc.name);
			},
			__("Shift Tools"),
		);
		frm.add_custom_button(
			__("Roster"),
			() => {
				window.location.href = "/hr/roster";
			},
			__("Shift Tools"),
		);
	},
});

// ---------------------------------------------------------------------------
// Shared CTC preview — the cumulative ladder used by Salary Structure,
// Salary Structure Assignment and the Bulk Assign tool. Kept here (app-wide
// bundle) so all three render an identical breakdown from one source.
// ---------------------------------------------------------------------------
$.extend(indian_hrms_compliance, {
	// A top-down cumulative ladder: each bold line is a real running subtotal,
	// and the muted "− X" row beneath shows what to subtract to reach the next
	// subtotal. Nothing is counted twice. Long-term provisions (Gratuity) sit
	// above CTC and are excluded from it. Uses CSS vars for dark-theme safety.
	render_ctc_ladder(m, fmt) {
		const info = (t) =>
			`<span class="text-muted" style="cursor:help;margin-left:4px" title="${frappe.utils.escape_html(
				t,
			)}">${frappe.utils.icon("help", "sm")}</span>`;
		const total = (label, val, tip, highlight) =>
			`<tr${highlight ? ' style="background:var(--control-bg)"' : ""}>
				<td style="color:var(--text-color)"><b>${label}</b>${tip ? info(tip) : ""}</td>
				<td class="text-right" style="color:var(--text-color)"><b>${fmt(val)}</b></td>
			</tr>`;
		const delta = (label, val, tip) =>
			`<tr class="text-muted">
				<td style="padding-left:1.75em">− ${label}${tip ? info(tip) : ""}</td>
				<td class="text-right">${fmt(val)}</td>
			</tr>`;

		const names = (pred, fallback) => {
			const n = m.earnings
				.filter((r) => r.statistical && pred(r) && r.amount)
				.map((r) => r.component);
			return n.length ? n.join(", ") : fallback;
		};
		const provNames = names((r) => r.exclude_from_ctc, __("Gratuity"));
		const emprNames = names((r) => !r.exclude_from_ctc, __("Employer PF / ESI"));

		let out = "";
		if (m.provisions) {
			out += total(
				__("Total cost to company"),
				m.total_cost,
				__("CTC plus long-term provisions ({0}) — the full cost including exit provisions.", [
					provNames,
				]),
				true,
			);
			out += delta(
				__("Long-term provisions ({0})", [provNames]),
				m.provisions,
				__("Accrued monthly but paid at exit (e.g. Gratuity). A real long-term liability, so it is kept out of CTC."),
			);
		}
		out += total(
			__("CTC (excl. long-term provisions)"),
			m.ctc,
			__("Gross earnings + employer statutory contributions ({0}). The standard cost-to-company.", [
				emprNames,
			]),
		);
		if (m.employer_ctc) {
			out += delta(
				__("Employer contributions ({0})", [emprNames]),
				m.employer_ctc,
				__("Employer's statutory share on top of gross — part of CTC, but not paid to the employee."),
			);
		}
		out += total(
			__("Gross Wages"),
			m.gross,
			__("Statutory wages payable before deductions (excludes any advance bonus)."),
		);
		if (m.bonus_advance) {
			out += delta(
				__("Statutory Bonus (Advance)"),
				m.bonus_advance,
				__("Paid in take-home, but shown separately as an advance against annual bonus — not wages."),
			);
		}
		if (m.total_deduction) {
			out += delta(
				__("Deductions"),
				m.total_deduction,
				__("Employee PF / ESI, Professional Tax and TDS withheld from gross."),
			);
		}
		out += total(
			__("Net Pay (take-home)"),
			m.net,
			__("What the employee actually receives in-hand."),
			true,
		);
		return out;
	},

	render_ctc_preview(m) {
		const fmt = (v) => format_currency(v, m.currency);
		const rows = (arr) =>
			arr
				.map(
					(r) => `
			<tr class="${r.statistical ? "text-muted" : ""}">
				<td>${frappe.utils.escape_html(r.component)}${
					r.statistical
						? ' <span class="indicator-pill gray">' + __("CTC · not paid") + "</span>"
						: ""
				}</td>
				<td class="text-right">${fmt(r.amount)}</td>
			</tr>`,
				)
				.join("");
		return `
			<div class="row">
				<div class="col-sm-6">
					<h6>${__("Earnings")}</h6>
					<table class="table table-bordered"><tbody>${rows(m.earnings)}</tbody></table>
				</div>
				<div class="col-sm-6">
					<h6>${__("Deductions")}</h6>
					<table class="table table-bordered"><tbody>${
						m.deductions.length
							? rows(m.deductions)
							: `<tr><td class="text-muted">${__("None")}</td><td></td></tr>`
					}</tbody></table>
				</div>
			</div>
			<table class="table table-bordered" style="margin-top:8px"><tbody>${indian_hrms_compliance.render_ctc_ladder(
				m,
				fmt,
			)}</tbody></table>`;
	},

	// Reusable "Preview CTC" dialog for a SAVED salary structure (Assignment /
	// Bulk Assign). Pass a default base / uan_number so it opens pre-filled with
	// the assignment's actual figures; the user can still tweak them live.
	show_ctc_preview(opts) {
		opts = opts || {};
		if (!opts.salary_structure) {
			frappe.msgprint(__("Select a Salary Structure first."));
			return;
		}
		const d = new frappe.ui.Dialog({
			title: opts.title || __("CTC Preview — {0}", [opts.salary_structure]),
			size: "large",
			fields: [
				{
					fieldname: "base",
					fieldtype: "Currency",
					label: __("Base (monthly gross)"),
					reqd: 1,
					default: opts.base || 0,
				},
				{
					fieldname: "uan_number",
					fieldtype: "Check",
					label: __("Has UAN (PF applies)"),
					default: opts.uan_number ? 1 : 0,
				},
				{ fieldname: "cb", fieldtype: "Column Break" },
				{
					fieldname: "variable",
					fieldtype: "Currency",
					label: __("Variable (optional)"),
					default: opts.variable || 0,
				},
				{ fieldname: "sb", fieldtype: "Section Break" },
				{ fieldname: "result", fieldtype: "HTML" },
			],
		});
		const render = () => {
			const base = d.get_value("base");
			if (!base) {
				d.fields_dict.result.$wrapper.html(
					`<div class="text-muted">${__("Enter a base to preview the CTC.")}</div>`,
				);
				return;
			}
			frappe
				.call({
					method: "indian_hrms_compliance.payroll.doctype.salary_structure.salary_structure.get_ctc_preview",
					args: {
						salary_structure: opts.salary_structure,
						base: base,
						uan_number: d.get_value("uan_number") ? 1 : 0,
						variable: d.get_value("variable") || 0,
					},
				})
				.then((r) => {
					if (r.message)
						d.fields_dict.result.$wrapper.html(
							indian_hrms_compliance.render_ctc_preview(r.message),
						);
				});
		};
		["base", "uan_number", "variable"].forEach((f) => {
			d.fields_dict[f].df.onchange = render;
		});
		d.show();
		render();
	},
});
