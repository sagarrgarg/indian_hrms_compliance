// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

// Risk tier -> control package. Picking a tier presets the completion/approval
// fields so authoring a task is ONE decision instead of six. The server
// (HRMSTask._apply_risk_tier) independently enforces the Critical invariant, so
// these presets are convenience — never the control itself.
const TIER_PRESETS = {
	Routine: {
		completion_type: "Checkbox",
		requires_attachment: 0,
		requires_approval: 0,
	},
	Standard: {
		// Evidence, but nobody's signature: proof without ceremony.
		requires_attachment: 1,
		requires_approval: 0,
	},
	Critical: {
		// Evidence + segregation of duties: the doer cannot approve.
		requires_attachment: 1,
		requires_approval: 1,
		approver_resolution: "Reports To",
	},
};

function tierHelp(tier) {
	return (
		{
			Routine: __("One tap to complete. No evidence, no approval — for everyday work."),
			Standard: __("Captures evidence (a file, a number, a note). No sign-off needed."),
			Critical: __(
				"Evidence plus approval by someone other than the doer. Use for money movement and statutory obligations.",
			),
		}[tier] || __("Pick a tier to preset how this task is completed and approved.")
	);
}

frappe.ui.form.on("HRMS Task", {
	refresh(frm) {
		frm.trigger("show_tier_help");

		if (frm.is_new()) {
			if (!frm.doc.risk_tier) frm.set_value("risk_tier", "Routine");
			return;
		}

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

	risk_tier(frm) {
		frm.trigger("show_tier_help");
		const preset = TIER_PRESETS[frm.doc.risk_tier];
		if (!preset) return;

		// Apply the package in full. Picking a LOWER tier is an explicit request
		// to drop that ceremony, so we honour it rather than half-applying and
		// leaving the server to raise the tier straight back (it converges tier
		// and controls upward, which would silently undo the user's choice).
		const droppedApproval = frm.doc.requires_approval && !preset.requires_approval;
		Object.entries(preset).forEach(([field, value]) => {
			if (frm.doc[field] !== value) frm.set_value(field, value);
		});

		// Removing a control is never silent.
		if (droppedApproval) {
			frappe.show_alert({
				message: __("{0} tier does not require approval — the approval step was removed.", [
					frm.doc.risk_tier,
				]),
				indicator: "orange",
			});
		}
	},

	show_tier_help(frm) {
		const field = frm.get_field("risk_tier");
		if (field) field.set_description(tierHelp(frm.doc.risk_tier));
	},

	requires_approval(frm) {
		// Turning approval OFF on a Critical task contradicts the tier; the server
		// re-enables it on save, so say so now rather than surprising them later.
		if (!frm.doc.requires_approval && frm.doc.risk_tier === "Critical") {
			frappe.show_alert({
				message: __("Critical tier always requires approval — it will be re-enabled on save."),
				indicator: "orange",
			});
		}
	},

	is_statutory(frm) {
		// Statutory = born Critical, locked. Reflect that the instant it's ticked;
		// the server enforces it on save regardless.
		if (frm.doc.is_statutory) {
			frm.set_value("risk_tier", "Critical");
			frappe.show_alert({
				message: __("Statutory task — risk tier locked at Critical (cannot be lowered)."),
				indicator: "red",
			});
		}
	},
});
