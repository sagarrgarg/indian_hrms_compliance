// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

// Renders the Employee "Accountability" lens on the Desk form — a computed view
// (no stored data) of what this person is answerable for. Makes handover visible
// at a glance and mirrors the leaver No-Dues gate's own signal.

frappe.ui.form.on("Employee", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call({
			method: "indian_hrms_compliance.api.accountability.get_accountability",
			args: { employee: frm.doc.name },
			callback: (r) => {
				const a = r.message;
				if (!a) return;
				const parts = [
					__("DRI of <b>{0}</b> active KRA(s)", [a.dri_kras.length]),
				];
				if (a.headed_departments.length)
					parts.push(__("Head of <b>{0}</b> department(s)", [a.headed_departments.length]));
				if (a.owned_playbooks.length)
					parts.push(__("Owns <b>{0}</b> playbook(s)", [a.owned_playbooks.length]));
				parts.push(__("<b>{0}</b> open task instance(s)", [a.open_task_instances]));
				parts.push(__("Approver on <b>{0}</b> task(s)", [a.approver_of]));

				const badge = a.is_clear
					? `<span style="color:#16a34a;font-weight:600">${__("✓ Clear for handover")}</span>`
					: `<span style="color:#dc2626;font-weight:600">${__("Handover blocked")}: ${frappe.utils.escape_html(
							a.blocking_reasons.join(", "),
						)}</span>`;

				const html = `<div style="line-height:1.9">${parts.join(
					" &nbsp;·&nbsp; ",
				)}<div style="margin-top:6px">${badge}</div></div>`;
				frm.dashboard.add_section(html, __("Accountability"));
			},
		});
	},
});
