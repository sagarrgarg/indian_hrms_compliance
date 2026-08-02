// Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Goal", {
	refresh(frm) {
		frm.trigger("set_filters");
		frm.trigger("add_custom_buttons");

		if (frm.doc.is_group) {
			frm.set_df_property(
				"progress",
				"description",
				__("Group goal's progress is auto-calculated based on the child goals."),
			);
		}
	},

	set_filters(frm) {
		frm.set_query("parent_goal", () => {
			return {
				filters: {
					is_group: 1,
					name: ["!=", frm.doc.name],
					employee: frm.doc.employee,
				},
			};
		});

		frm.set_query("kra", () => {
			return {
				query: "indian_hrms_compliance.hr.doctype.appraisal.appraisal.get_kras_for_employee",
				filters: {
					employee: frm.doc.employee,
					appraisal_cycle: frm.doc.appraisal_cycle,
				},
			};
		});

		frm.set_query("appraisal_cycle", () => {
			return {
				filters: {
					status: ["!=", "Completed"],
					company: frm.doc.company,
				},
			};
		});
	},

	add_custom_buttons(frm) {
		if (frm.doc.__islocal || frm.doc.status === "Completed") return;
		const doc_status = frm.doc.status;

		if (doc_status === "Archived") {
			frm.add_custom_button(
				__("Unarchive"),
				() => {
					frm.set_value("status", "");
					frm.save();
				},
				__("Status"),
			);
		}

		if (doc_status === "Closed") {
			frm.add_custom_button(
				__("Reopen"),
				() => {
					frm.set_value("status", "");
					frm.save();
				},
				__("Status"),
			);
		}

		if (doc_status !== "Archived") {
			frm.add_custom_button(
				__("Archive"),
				() => {
					frm.set_value("status", "Archived");
					frm.save();
				},
				__("Status"),
			);
		}

		if (doc_status !== "Closed") {
			frm.add_custom_button(
				__("Close"),
				() => {
					frm.set_value("status", "Closed");
					frm.save();
				},
				__("Status"),
			);
		}

		// Task-instance routing: delegate an open instance to a direct report, or
		// pull it back to yourself. Server enforces who-can-do-what; these are just
		// the entry points, mirrored in the PWA task view.
		const routable =
			frm.doc.goal_type === "Task Instance" &&
			!["Completed", "Closed", "Archived"].includes(doc_status);
		if (routable) {
			frm.add_custom_button(
				__("Delegate…"),
				() => {
					const d = new frappe.ui.Dialog({
						title: __("Delegate task"),
						fields: [
							{
								fieldname: "employee",
								fieldtype: "Link",
								options: "Employee",
								label: __("To (your direct report)"),
								reqd: 1,
								get_query: () => ({
									filters: { status: "Active", company: frm.doc.company },
								}),
							},
						],
						primary_action_label: __("Delegate"),
						primary_action(values) {
							frappe.call({
								method: "indian_hrms_compliance.api.reassign_task_instance",
								args: { goal_name: frm.doc.name, to_employee: values.employee },
								freeze: true,
								callback: () => {
									d.hide();
									frappe.show_alert({ message: __("Delegated"), indicator: "green" });
									frm.reload_doc();
								},
							});
						},
					});
					d.show();
				},
				__("Assign"),
			);
			frm.add_custom_button(
				__("Assign to me"),
				() => {
					frappe.call({
						method: "indian_hrms_compliance.api.reassign_task_instance",
						args: { goal_name: frm.doc.name },
						freeze: true,
						callback: () => {
							frappe.show_alert({ message: __("Assigned to you"), indicator: "green" });
							frm.reload_doc();
						},
					});
				},
				__("Assign"),
			);
		}

		// Make the linked Playbook (SOP) one click away for the doer: the playbook
		// lives on the task template, so resolve it and open the steps as a
		// checklist dialog (mirrors the PWA task view's inline checklist).
		if (frm.doc.goal_type === "Task Instance" && frm.doc.task_template) {
			frappe.db
				.get_value("HRMS Task", frm.doc.task_template, "playbook")
				.then((r) => {
					const pb = r && r.message && r.message.playbook;
					if (!pb) return;
					frm.add_custom_button(__("View Playbook (SOP)"), () => {
						frappe.call({
							method: "indian_hrms_compliance.hr.doctype.playbook.playbook.get_playbook_steps",
							args: { playbook: pb },
							callback: (res) => {
								const d = res.message || {};
								const steps = d.steps || [];
								if (!steps.length) {
									frappe.msgprint(__("This playbook has no steps yet."));
									return;
								}
								const rows = steps
									.map((s, i) => {
										const cp = s.is_control_point
											? ` <span style="color:#b45309;font-weight:600;">&#128274; ${__("Control point")}</span>`
											: "";
										const ev = s.expected_evidence
											? `<div style="color:#6b7280;font-size:11px;">${__("Evidence")}: ${frappe.utils.escape_html(s.expected_evidence)}</div>`
											: "";
										return `<tr><td style="padding:4px 8px;vertical-align:top;color:#9ca3af;">${i + 1}</td><td style="padding:4px 8px;border-bottom:1px solid #f3f4f6;">${frappe.utils.escape_html(s.step_text || "")}${cp}${ev}</td></tr>`;
									})
									.join("");
								const dlg = new frappe.ui.Dialog({
									title: `${d.title || __("Playbook")}${d.version ? " · v" + d.version : ""}`,
									size: "large",
									fields: [{ fieldtype: "HTML", fieldname: "html" }],
								});
								dlg.fields_dict.html.$wrapper.html(
									`<table style="width:100%;border-collapse:collapse;">${rows}</table>`,
								);
								dlg.show();
							},
						});
					});
				});
		}
	},

	kra(frm) {
		if (!frm.doc.appraisal_cycle) {
			frm.set_value("kra", "");

			frappe.msgprint({
				message: __("Please select the Appraisal Cycle first."),
				title: __("Mandatory"),
			});

			return;
		}

		if (frm.doc.__islocal || !frm.doc.is_group) return;

		let msg = __(
			"Changing KRA in this parent goal will align all the child goals to the same KRA, if any.",
		);
		msg += "<br>";
		msg += __("Do you still want to proceed?");

		frappe.confirm(
			msg,
			() => {},
			() => {
				frappe.db.get_value("Goal", frm.doc.name, "kra", (r) =>
					frm.set_value("kra", r.kra),
				);
			},
		);
	},

	is_group(frm) {
		if (frm.doc.__islocal && frm.doc.is_group) {
			frm.set_value("progress", 0);
		}
	},
});
