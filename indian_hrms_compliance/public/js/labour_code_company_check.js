// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Company", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(
			__("Check Labour Code Compliance"),
			() => {
				frappe
					.call({
						method:
							"indian_hrms_compliance.overrides.labour_code_applicability.get_labour_code_applicability",
						args: { company: frm.doc.name },
					})
					.then((r) => {
						if (!r.message) return;
						const app = r.message;
						let rows = "";
						(app.checklist || []).forEach((row) => {
							const color =
								row.status === "OK"
									? "green"
									: row.status === "Missing"
										? "red"
										: row.status === "Action Required"
											? "orange"
											: "grey";
							rows += `<tr>
								<td style='padding:4px 8px;border:1px solid #ddd'>${row.requirement}</td>
								<td style='padding:4px 8px;border:1px solid #ddd'>${row.required ? "Yes" : "No"}</td>
								<td style='padding:4px 8px;border:1px solid #ddd'>${row.present === null ? "—" : row.present ? "Yes" : "No"}</td>
								<td style='padding:4px 8px;border:1px solid #ddd;color:${color};font-weight:bold'>${row.status}</td>
							</tr>`;
						});
						const dialog = new frappe.ui.Dialog({
							title: __("Labour Code Compliance — {0}", [frm.doc.name]),
							size: "large",
							fields: [
								{
									fieldtype: "HTML",
									fieldname: "summary",
									options: `
										<p><b>Active workers:</b> ${app.worker_count}</p>
										<table style='border-collapse:collapse;width:100%'>
											<thead><tr style='background:#f5f5f5'>
												<th style='padding:6px 8px;border:1px solid #ddd;text-align:left'>Requirement</th>
												<th style='padding:6px 8px;border:1px solid #ddd'>Required</th>
												<th style='padding:6px 8px;border:1px solid #ddd'>Present</th>
												<th style='padding:6px 8px;border:1px solid #ddd'>Status</th>
											</tr></thead>
											<tbody>${rows}</tbody>
										</table>
									`,
								},
							],
						});
						dialog.show();
					});
			},
			__("Compliance"),
		);
	},
});
