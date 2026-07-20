// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("HRMS Task", {
	refresh(frm) {
		if (frm.is_new()) return;

		// Dry-run: post a single Task Instance now so you can verify the whole
		// process (assignment, period, due date, notification) end-to-end.
		frm.add_custom_button(
			__("Create Test Instance"),
			() => {
				frappe.confirm(
					__(
						"Post one Task Instance now for a single assigned employee, to verify the process is working? It won't duplicate if that instance already exists.",
					),
					() => {
						frm.call("create_test_instance")
							.then((r) => {
								const d = r.message;
								if (!d) return;
								const link = `<a href="/app/goal/${encodeURIComponent(d.goal)}" target="_blank">${frappe.utils.escape_html(d.goal || "")}</a>`;
								frappe.msgprint({
									title: d.created
										? __("Test Instance Created ✅")
										: __("Instance Already Exists"),
									indicator: d.created ? "green" : "blue",
									message: `
										${__("Goal")}: ${link}<br>
										${__("Employee")}: ${frappe.utils.escape_html(d.employee_name || d.employee)}
										${d.candidate_count > 1 ? ` <span style="color:#888">(1 of ${d.candidate_count} matched)</span>` : ""}<br>
										${__("Period")}: ${frappe.utils.escape_html(d.period)}<br>
										${__("Due")}: <b>${d.due_date}</b>`,
								});
							})
							.catch(() => {});
					},
				);
			},
			__("Verify"),
		);
	},
});
