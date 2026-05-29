// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// On Desk startup: if the current user has any overdue policy acknowledgements,
// show a modal listing them with a quick "Open" action. Once acknowledged
// (or until the page is reloaded next day), the popup doesn't return for the
// same items.
// Skipped for Guest/Administrator.

$(document).on("app_ready", () => {
	try {
		_indian_hrms_check_overdue_policy_acks();
	} catch (e) {
		console.warn("indian_hrms_compliance overdue policy check failed:", e);
	}
});

function _indian_hrms_check_overdue_policy_acks() {
	const ctx = (frappe.boot && frappe.boot.indian_hrms_compliance) || {};
	const overdue = ctx.overdue_policy_acks || [];
	if (!overdue.length) return;

	// Suppress for Administrator (it's noisy during dev)
	if (frappe.session.user === "Administrator") return;

	// Suppress if user dismissed within this session
	if (sessionStorage.getItem("ihc_overdue_dismissed") === "1") return;

	const rows = overdue
		.map((a) => {
			const link = `<a href="/app/employee-policy-acknowledgement/${a.name}">Open</a>`;
			return `<tr>
				<td>${frappe.utils.escape_html(a.policy_name_fetched || a.policy)}</td>
				<td>${frappe.utils.escape_html(a.policy_version || "")}</td>
				<td>${frappe.utils.escape_html(a.policy_category || "")}</td>
				<td style="color:#c0392b;"><strong>${a.due_date}</strong></td>
				<td>${link}</td>
			</tr>`;
		})
		.join("");

	const html = `
		<div>
			<p style="margin-bottom:12px;">
				You have <strong>${overdue.length}</strong> policy acknowledgement(s)
				past the due date. Please review and acknowledge each one.
			</p>
			<table class="table table-bordered" style="font-size:13px;">
				<thead>
					<tr>
						<th>Policy</th>
						<th>Version</th>
						<th>Category</th>
						<th>Due</th>
						<th></th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		</div>
	`;

	const dialog = new frappe.ui.Dialog({
		title: __("Overdue Policy Acknowledgements"),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "overdue_html", options: html }],
		primary_action_label: __("Open My Pending Acknowledgements"),
		primary_action() {
			frappe.set_route("List", "Employee Policy Acknowledgement", { status: "Pending" });
			dialog.hide();
		},
		secondary_action_label: __("Dismiss for this session"),
		secondary_action() {
			sessionStorage.setItem("ihc_overdue_dismissed", "1");
			dialog.hide();
		},
	});
	dialog.show();
}
