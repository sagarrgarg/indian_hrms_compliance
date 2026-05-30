// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// Data Erasure Request — "Execute Erasure" button on Decision Made.
// Workflow buttons (Send for Legal Review / Record Legal Outcome /
// Reject) are auto-rendered by the Workflow.
frappe.ui.form.on("Data Erasure Request", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.workflow_state === "Decision Made" &&
		    ["Approved Full", "Approved Partial"].includes(frm.doc.decision)) {
			frm.add_custom_button(
				__("Execute Erasure"),
				() => {
					frappe.confirm(
						__(
							"This will anonymise the agreed personal data fields on the Employee record. " +
							"This action is logged in Data Access Log and cannot be reversed. Continue?"
						),
						() => {
							frappe.call({
								method: "indian_hrms_compliance.hr.doctype.data_erasure_request.data_erasure_request.execute_erasure",
								args: { name: frm.doc.name },
								freeze: true,
								freeze_message: __("Executing erasure..."),
								callback: (r) => {
									if (r.message) {
										frappe.msgprint(
											__("Erasure executed: {0} field(s) anonymised.",
												[r.message.touched_count]
											)
										);
										frm.reload_doc();
									}
								},
							});
						}
					);
				},
				__("DPDP")
			);
		}
	},
});
