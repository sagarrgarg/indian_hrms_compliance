// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

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
