// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

// Shared form helpers for any doctype that carries a `cadence_schedule` child
// table (Compliance Return Definition, HRMS Task, …). Adds two buttons under a
// "Cadence" group: generate a starter schedule, and preview the exact dates the
// current rows resolve to. Registered for each host doctype via doctype_js.

frappe.provide("indian_hrms_compliance.cadence");

indian_hrms_compliance.cadence.setup = function (frm) {
	if (!frm.fields_dict.cadence_schedule) return;

	frm.add_custom_button(
		__("Generate rows…"),
		() => indian_hrms_compliance.cadence.generate_dialog(frm),
		__("Cadence"),
	);

	frm.add_custom_button(
		__("Preview dates"),
		() => indian_hrms_compliance.cadence.preview_dialog(frm),
		__("Cadence"),
	);
};

indian_hrms_compliance.cadence.generate_dialog = function (frm) {
	const d = new frappe.ui.Dialog({
		title: __("Generate Cadence Schedule"),
		fields: [
			{
				fieldname: "cadence",
				label: __("Cadence"),
				fieldtype: "Select",
				options: ["Monthly", "Quarterly", "Half-Yearly", "Annually"].join("\n"),
				default: "Monthly",
				reqd: 1,
			},
			{
				fieldname: "due_day",
				label: __("Due Day (0 = last day of month)"),
				fieldtype: "Int",
				default: 0,
			},
			{
				fieldname: "due_month_offset",
				label: __("Months after period end the due date falls"),
				fieldtype: "Int",
				default: 1,
				description: __("GST → 1 (next month). Same-period due → 0."),
			},
			{
				fieldname: "label_prefix",
				label: __("Occurrence Label Prefix"),
				fieldtype: "Data",
				description: __("e.g. GSTR3B- → GSTR3B-Apr, GSTR3B-May, …"),
			},
			{
				fieldname: "replace",
				label: __("Replace existing rows"),
				fieldtype: "Check",
				default: 1,
			},
		],
		primary_action_label: __("Generate"),
		primary_action(values) {
			frappe
				.call({
					method: "indian_hrms_compliance.utils.cadence_api.generate_schedule_rows",
					args: {
						cadence: values.cadence,
						due_day: values.due_day || 0,
						due_month_offset: values.due_month_offset ?? 1,
						label_prefix: values.label_prefix || "",
					},
				})
				.then((r) => {
					const rows = r.message || [];
					if (!rows.length) {
						frappe.msgprint(__("No rows generated for this cadence."));
						return;
					}
					if (values.replace) frm.clear_table("cadence_schedule");
					rows.forEach((row) => {
						const child = frm.add_child("cadence_schedule");
						Object.assign(child, row);
					});
					frm.set_value("use_cadence_schedule", 1);
					frm.refresh_field("cadence_schedule");
					d.hide();
					frappe.show_alert({
						message: __("{0} occurrence rows added — tweak any irregular dates, then save.", [
							rows.length,
						]),
						indicator: "green",
					});
				});
		},
	});
	d.show();
};

indian_hrms_compliance.cadence.preview_dialog = function (frm) {
	const rows = (frm.doc.cadence_schedule || []).map((r) => ({
		occurrence_label: r.occurrence_label,
		active: r.active,
		period_start_month: r.period_start_month,
		period_start_year_index: r.period_start_year_index,
		period_end_month: r.period_end_month,
		period_end_year_index: r.period_end_year_index,
		due_month: r.due_month,
		due_day: r.due_day,
		due_year_index: r.due_year_index,
	}));
	if (!rows.length) {
		frappe.msgprint(__("Add some Cadence Schedule rows first."));
		return;
	}
	frappe
		.call({
			method: "indian_hrms_compliance.utils.cadence_api.preview_schedule",
			args: { rows: JSON.stringify(rows) },
		})
		.then((r) => {
			const data = r.message || {};
			const occ = data.occurrences || [];
			const body = `
				<p>${__("Resolved for")} <b>${frappe.utils.escape_html(data.fy_label || "")}</b>
				${__("(dates shift by whole years for other FYs)")}.</p>
				<table class="table table-bordered" style="font-size:13px">
					<thead><tr>
						<th>${__("Occurrence")}</th><th>${__("Period")}</th><th>${__("Due Date")}</th>
					</tr></thead>
					<tbody>
						${occ
							.map(
								(o) => `<tr>
									<td>${frappe.utils.escape_html(o.label)}</td>
									<td>${o.period_start} → ${o.period_end}</td>
									<td><b>${o.due_date}</b></td>
								</tr>`,
							)
							.join("")}
					</tbody>
				</table>`;
			new frappe.ui.Dialog({
				title: __("Cadence Preview — {0} occurrences", [occ.length]),
				fields: [{ fieldtype: "HTML", options: body }],
			}).show();
		});
};

frappe.ui.form.on("Compliance Return Definition", {
	refresh: (frm) => indian_hrms_compliance.cadence.setup(frm),
});

frappe.ui.form.on("HRMS Task", {
	refresh: (frm) => indian_hrms_compliance.cadence.setup(frm),
});
