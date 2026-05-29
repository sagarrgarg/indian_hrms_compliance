// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// On Desk startup: if the current user has any overdue Task Instances,
// show a modal listing them. Same UX shape as the overdue policy popup.

$(document).on("app_ready", () => {
	try {
		_indian_hrms_check_overdue_tasks();
	} catch (e) {
		console.warn("indian_hrms_compliance overdue task check failed:", e);
	}
});

function _indian_hrms_check_overdue_tasks() {
	const ctx = (frappe.boot && frappe.boot.indian_hrms_compliance) || {};
	const overdue = ctx.overdue_task_instances || [];
	if (!overdue.length) return;
	if (frappe.session.user === "Administrator") return;
	if (sessionStorage.getItem("ihc_overdue_task_dismissed") === "1") return;

	const rows = overdue
		.map((t) => {
			const link = `<a href="/app/goal/${t.name}">Open</a>`;
			return `<tr>
				<td>${frappe.utils.escape_html(t.goal_name || t.task_template || t.name)}</td>
				<td>${frappe.utils.escape_html(t.kra || "")}</td>
				<td>${frappe.utils.escape_html(t.period_label || "")}</td>
				<td style="color:#c0392b;"><strong>${t.due_date}</strong></td>
				<td>${link}</td>
			</tr>`;
		})
		.join("");

	const html = `
		<div>
			<p style="margin-bottom:12px;">
				You have <strong>${overdue.length}</strong> task(s) past the due date.
				Please complete or report on each one.
			</p>
			<table class="table table-bordered" style="font-size:13px;">
				<thead>
					<tr>
						<th>Task</th>
						<th>KRA</th>
						<th>Period</th>
						<th>Due</th>
						<th></th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		</div>
	`;

	const dialog = new frappe.ui.Dialog({
		title: __("Overdue Tasks"),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "overdue_html", options: html }],
		primary_action_label: __("Open My Tasks"),
		primary_action() {
			frappe.set_route("List", "Goal", {
				goal_type: "Task Instance",
				status: ["in", ["Pending", "In Progress"]],
			});
			dialog.hide();
		},
		secondary_action_label: __("Dismiss for this session"),
		secondary_action() {
			sessionStorage.setItem("ihc_overdue_task_dismissed", "1");
			dialog.hide();
		},
	});
	dialog.show();
}
