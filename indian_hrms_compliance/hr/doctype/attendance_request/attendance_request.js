// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

const API = "indian_hrms_compliance.api";

frappe.ui.form.on("Attendance Request", {
	refresh(frm) {
		frm.trigger("show_attendance_warnings");
		frm.trigger("setup_approval_actions");
	},

	// Replace the raw "Submit" action with an explicit approval decision.
	// Submitting IS approving (it creates the Attendance records), so exposing
	// Submit alongside Approve/Reject would be two names for one action and
	// would bypass the comment + status trail.
	setup_approval_actions(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 0) return;

		frm.page.clear_primary_action();

		// Decided drafts (Rejected / Needs Clarification) are terminal or are
		// back with the employee — no approver action from here.
		const status = frm.doc.status;
		if (status && !["Open", "Draft"].includes(status)) return;

		frm.add_custom_button(__("Reject"), () => decide(frm, "reject"));
		frm.add_custom_button(__("Ask for Clarification"), () => decide(frm, "clarify"));
		frm.page.set_primary_action(__("Approve"), () => decide(frm, "approve"));
	},

	show_attendance_warnings(frm) {
		if (!frm.is_new() && frm.doc.docstatus === 0) {
			frm.dashboard.clear_headline();

			frm.call("get_attendance_warnings").then((r) => {
				if (r.message?.length) {
					frm.dashboard.reset();
					frm.dashboard.add_section(
						frappe.render_template("attendance_warnings", {
							warnings: r.message || [],
						}),
						__("Attendance Warnings"),
					);
					frm.dashboard.show();
				}
			});
		}
	},
});

const ACTIONS = {
	approve: {
		method: `${API}.approve_request`,
		commentRequired: false,
		success: "Approved",
	},
	reject: {
		method: `${API}.reject_request`,
		commentRequired: true,
		success: "Rejected",
	},
	clarify: {
		method: `${API}.request_attendance_clarification`,
		commentRequired: true,
		success: "Sent back for clarification",
	},
};

const LABELS = {
	approve: {
		title: "Approve Attendance Request",
		button: "Approve",
		description: "Attendance will be marked for the requested days.",
	},
	reject: {
		title: "Reject Attendance Request",
		button: "Reject",
		description: "The employee will see this reason on their request.",
	},
	clarify: {
		title: "Ask for Clarification",
		button: "Send Back",
		description: "The request goes back to the employee, who can edit and resubmit it.",
	},
};

function decide(frm, action) {
	const cfg = ACTIONS[action];
	const text = LABELS[action];

	const dialog = new frappe.ui.Dialog({
		title: __(text.title),
		fields: [
			{
				fieldtype: "Small Text",
				fieldname: "comment",
				label: __("Comment"),
				reqd: cfg.commentRequired ? 1 : 0,
				description: __(text.description),
			},
		],
		primary_action_label: __(text.button),
		primary_action(values) {
			const comment = (values.comment || "").trim();
			if (cfg.commentRequired && !comment) {
				frappe.msgprint(__("A comment is required."));
				return;
			}
			dialog.hide();
			frappe.dom.freeze(__("Working..."));

			// clarify takes (name, comment); approve/reject take (doctype, name, comment)
			const args =
				action === "clarify"
					? { name: frm.doc.name, comment: comment }
					: {
							doctype: frm.doc.doctype,
							name: frm.doc.name,
							comment: comment || null,
					  };

			frappe
				.call({ method: cfg.method, args: args })
				.then((r) => {
					frappe.dom.unfreeze();
					if (r.exc) return;
					frappe.show_alert({ message: __(cfg.success), indicator: "green" });
					frm.reload_doc();
				})
				.catch(() => frappe.dom.unfreeze());
		},
	});

	dialog.show();
}
