// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

const assignable_masters = {};

function get_assignment_actions() {
	return [
		{
			label: __("Holiday List"),
			doctype: "Holiday List Assignment",
			master_field: "holiday_list",
			prefill: (frm) => ({
				applicable_for: "Employee",
				assigned_to: frm.doc.name,
				employee_name: frm.doc.employee_name,
				employee_company: frm.doc.company,
			}),
			hide: ["naming_series"],
			on_change: {
				holiday_list: sync_holiday_list_range,
				from_date: flag_start_date_outside_range,
			},
		},
		{
			label: __("Leave Policy"),
			doctype: "Leave Policy Assignment",
			master: "Leave Policy",
			master_field: "leave_policy",
			prefill: (frm) => ({ employee: frm.doc.name }),
			queries: (frm) => ({
				leave_policy: { docstatus: 1 },
				leave_period: { is_active: 1, company: frm.doc.company },
			}),
			on_change: {
				assignment_based_on: set_leave_effective_dates,
				leave_period: set_leave_effective_dates,
			},
		},
		{
			label: __("Salary Structure"),
			doctype: "Salary Structure Assignment",
			master: "Salary Structure",
			prefill: (frm) => ({ employee: frm.doc.name, company: frm.doc.company }),
			redirect: true,
		},
		{
			label: __("Shift"),
			doctype: "Shift Assignment",
			prefill: (frm) => ({ employee: frm.doc.name, company: frm.doc.company }),
			redirect: true,
		},
		{
			label: __("Shift Schedule"),
			doctype: "Shift Schedule Assignment",
			master: "Shift Schedule",
			prefill: (frm) => ({ employee: frm.doc.name, company: frm.doc.company }),
			redirect: true,
		},
	];
}

function get_assignable_masters(company) {
	if (!assignable_masters[company]) {
		assignable_masters[company] = frappe
			.xcall("indian_hrms_compliance.overrides.employee_master.get_assignable_masters", { company })
			.catch(() => {
				delete assignable_masters[company];
				return {};
			});
	}

	return assignable_masters[company];
}

function open_assignment(frm, action) {
	if (action.redirect) return frappe.new_doc(action.doctype, action.prefill(frm));

	frappe.model.with_doctype(action.doctype, () => {
		const doc = Object.assign(
			frappe.model.get_new_doc(action.doctype, null, null, true),
			action.prefill(frm),
		);

		frappe.ui.form.make_quick_entry(
			action.doctype,
			(created_doc) => notify_assignment_created(action, created_doc),
			(dialog) => setup_dialog(dialog, action, frm),
			doc,
			true,
		);
	});
}

function setup_dialog(dialog, action, frm) {
	for (const [fieldname, filters] of Object.entries(action.queries?.(frm) || {}))
		dialog.set_query(fieldname, () => ({ filters }));

	for (const fieldname of action.hide || []) {
		const control = dialog.fields_dict[fieldname];
		if (!control) continue;

		control.df = { ...control.df, hidden: 1 };
		control.refresh();
	}

	for (const [fieldname, handler] of Object.entries(action.on_change || {})) {
		const control = dialog.fields_dict[fieldname];
		if (!control) continue;

		control.df = { ...control.df, onchange: () => handler(dialog, frm) };
	}

	dialog.add_custom_action(__("Edit Full Form"), () => dialog.open_doc(false));
	keep_dialog_open_for_submit(dialog);
}

function keep_dialog_open_for_submit(dialog) {
	dialog.set_primary_action(__("Save"), () => {
		if (dialog.working || !dialog.get_values()) return;

		dialog.working = true;
		dialog.insert().finally(() => (dialog.working = false));
	});
}

function set_field_hint(dialog, fieldname, title) {
	dialog.modal_body.find(".assignment-hint").remove();
	if (!title) return;

	frappe.ui
		.alert({ title, theme: "blue", css_class: "assignment-hint" })
		.insertAfter(dialog.fields_dict[fieldname].$wrapper);
}

async function sync_holiday_list_range(dialog) {
	const holiday_list = dialog.get_value("holiday_list");
	dialog.holiday_list_range = null;

	if (holiday_list) {
		const response = await frappe.db.get_value("Holiday List", holiday_list, [
			"from_date",
			"to_date",
		]);
		dialog.holiday_list_range = response.message?.from_date ? response.message : null;
	}

	const range_start = dialog.holiday_list_range?.from_date;
	if (range_start && !dialog.get_value("from_date"))
		await dialog.set_value("from_date", range_start);

	flag_start_date_outside_range(dialog);
}

async function set_leave_effective_dates(dialog, frm) {
	const assignment_based_on = dialog.get_value("assignment_based_on");

	if (!assignment_based_on) {
		await dialog.set_value("effective_from", "");
		await dialog.set_value("effective_to", "");
		return;
	}

	if (assignment_based_on === "Joining Date") {
		await dialog.set_value("effective_from", frm.doc.date_of_joining);
		await dialog.set_value(
			"effective_to",
			frappe.datetime.add_months(frm.doc.date_of_joining, 12),
		);
		return;
	}

	const leave_period = dialog.get_value("leave_period");
	if (!leave_period) return;

	const response = await frappe.db.get_value("Leave Period", leave_period, [
		"from_date",
		"to_date",
	]);
	if (!response.message) return;

	await dialog.set_value("effective_from", response.message.from_date);
	await dialog.set_value("effective_to", response.message.to_date);
}

function flag_start_date_outside_range(dialog) {
	const range = dialog.holiday_list_range;
	const from_date = dialog.get_value("from_date");
	if (!range || !from_date) return set_field_hint(dialog, "from_date", null);

	const outside =
		frappe.datetime.get_diff(from_date, range.from_date) < 0 ||
		frappe.datetime.get_diff(from_date, range.to_date) > 0;

	set_field_hint(
		dialog,
		"from_date",
		outside &&
			__("Assignment must start between {0} and {1}", [
				frappe.datetime.str_to_user(range.from_date),
				frappe.datetime.str_to_user(range.to_date),
			]),
	);
}

function notify_assignment_created(action, doc) {
	frappe.quick_entry?.hide();

	const master_doctype = frappe.meta.get_docfield(action.doctype, action.master_field).options;

	frappe.show_alert({
		message: __("{0} was assigned {1}", [
			__(master_doctype),
			frappe.utils.get_form_link(action.doctype, doc.name, true),
		]),
		indicator: "green",
	});
}

frappe.ui.form.on("Employee", {
	refresh: function (frm) {
		if (!frm.is_new()) frm.trigger("render_setup_status");

		frm.set_query("payroll_cost_center", function () {
			return {
				filters: {
					company: frm.doc.company,
					is_group: 0,
				},
			};
		});

		// filter advance account based on salary currency
		if (frm.doc.salary_currency) {
			frm.set_query("employee_advance_account", function () {
				return {
					filters: {
						root_type: "Asset",
						is_group: 0,
						company: frm.doc.company,
						account_currency: frm.doc.salary_currency,
						account_type: "Receivable",
					},
				};
			});
		}
		frm.set_df_property("holiday_list", "hidden", 1);
		// Reporting Manager must be an Active employee of the same company.
		frm.set_query("reports_to", function () {
			return {
				filters: {
					company: frm.doc.company,
					status: "Active",
				},
			};
		});

		// Approvers must be Active employees of the same company who also have a
		// linked User — the approval engine acts on the User, so a userless
		// Employee can never approve.
		["expense_approver", "leave_approver", "shift_request_approver"].forEach((field) => {
			frm.set_query(field, function () {
				return {
					filters: {
						company: frm.doc.company,
						status: "Active",
						user_id: ["is", "set"],
					},
				};
			});
		});

		// hide naming series field based on hr settings
		frappe.db.get_single_value("HR Settings", "emp_created_by").then((value) => {
			frm.toggle_display("naming_series", value === "Naming Series");
		});

		frm.trigger("add_assignment_actions");
		frm.trigger("setup_biometric_id");
	},

	add_assignment_actions: async function (frm) {
		if (frm.is_new() || frm.doc.status !== "Active") return;

		const available_masters = await get_assignable_masters(frm.doc.company);

		for (const action of get_assignment_actions()) {
			if (action.master && !available_masters[action.master]) continue;
			if (!frappe.model.can_create(action.doctype)) continue;

			frm.add_custom_button(
				action.label,
				() => open_assignment(frm, action),
				__("Create Assignments"),
			);
		}
	},

	setup_biometric_id(frm) {
		// Drive the attendance_device_id (Biometric / RF tag ID) UX from
		// HR Settings.biometric_id_mode. The field is unique and, once set, is
		// locked to System Managers; server-side rules in apply_biometric_id_rules
		// enforce this — the form just mirrors it for a clean UX.
		const fieldname = "attendance_device_id";
		if (!frm.fields_dict[fieldname]) return;

		const is_sys_mgr = (frappe.user_roles || []).includes("System Manager");
		const has_value = !!(frm.doc[fieldname] && String(frm.doc[fieldname]).trim());
		const can_write = frm.perm && frm.perm[0] && frm.perm[0].write;

		frappe.db.get_single_value("HR Settings", "biometric_id_mode").then((mode) => {
			mode = mode || "Manual";

			// Read-only once a value exists (unless System Manager); always
			// read-only in compulsory-auto mode for non-System-Managers.
			let read_only = has_value && !is_sys_mgr;
			if (mode === "Auto (Compulsory)" && !is_sys_mgr) read_only = true;
			frm.set_df_property(fieldname, "read_only", read_only ? 1 : 0);

			// Offer Generate when the system may assign and the field is empty.
			if ((mode === "Auto (Compulsory)" || mode === "Hybrid") && !has_value && can_write) {
				frm.add_custom_button(__("Generate Biometric ID"), () => {
					frappe.call({
						method: "indian_hrms_compliance.overrides.employee_master.generate_biometric_id",
					}).then((r) => {
						if (r && r.message) frm.set_value(fieldname, r.message);
					});
				});
			}
		});
	},

	date_of_birth(frm) {
		frm.call({
			method: "indian_hrms_compliance.overrides.employee_master.get_retirement_date",
			args: {
				date_of_birth: frm.doc.date_of_birth,
			},
		}).then((r) => {
			if (r && r.message) frm.set_value("date_of_retirement", r.message);
		});
	},

	render_setup_status(frm) {
		const field = frm.fields_dict.employee_readiness_html;
		if (!field) return;
		frappe.call({
			method: "indian_hrms_compliance.overrides.employee_master.get_employee_readiness",
			args: { employee: frm.doc.name },
			callback: function (r) {
				const d = r.message;
				if (!d || !d.categories) return;
				const s = d.score || {};
				const barColor = s.ready ? "#1f8c4d" : s.pct >= 60 ? "#d97706" : "#c0392b";
				const pill = s.ready
					? `<span style="background:#e7f6ec;color:#1f8c4d;padding:2px 10px;border-radius:999px;font-weight:600;">${__("Ready")}</span>`
					: `<span style="background:#fdecec;color:#c0392b;padding:2px 10px;border-radius:999px;font-weight:600;">${s.critical_open} ${__("critical pending")}</span>`;

				let html = `<div style="max-width:720px;">
					<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
						<strong style="font-size:15px;">${__("Setup Readiness")}: ${s.done}/${s.total} (${s.pct}%)</strong>
						${pill}
					</div>
					<div style="height:8px;background:#eee;border-radius:999px;overflow:hidden;margin-bottom:16px;">
						<div style="height:100%;width:${s.pct}%;background:${barColor};"></div>
					</div>`;

				d.categories.forEach((cat) => {
					html += `<div style="margin-bottom:14px;">
						<div style="font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#888;margin-bottom:6px;">${frappe.utils.escape_html(cat.name)}</div>`;
					cat.items.forEach((it) => {
						const icon = it.done
							? '<span style="color:#1f8c4d;">&#10003;</span>'
							: '<span style="color:#c0392b;">&#10007;</span>';
						const star = it.critical ? ' <span style="color:#c0392b;" title="Critical">*</span>' : "";
						const link = it.route
							? `<a href="#" class="ihc-rd-link" data-route='${JSON.stringify(it.route)}'>${__("Open")}</a>`
							: "";
						const hint = it.hint ? `<div style="font-size:11px;color:#aaa;">${frappe.utils.escape_html(it.hint)}</div>` : "";
						html += `<div style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid #f4f4f4;">
							<span style="width:16px;text-align:center;">${icon}</span>
							<span style="flex:1;">${frappe.utils.escape_html(it.label)}${star}${hint}</span>
							${link}
						</div>`;
					});
					html += `</div>`;
				});
				html += `</div>`;

				field.$wrapper.html(html);
				field.$wrapper.find(".ihc-rd-link").on("click", function (e) {
					e.preventDefault();
					frappe.set_route(...JSON.parse($(this).attr("data-route")));
				});
			},
		});
	},
});
