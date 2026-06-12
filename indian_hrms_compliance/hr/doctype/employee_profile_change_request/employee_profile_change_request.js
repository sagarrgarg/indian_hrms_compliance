// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

const PCR_DOCTYPE = "Employee Profile Change Request";
const APPROVE_METHOD =
	"indian_hrms_compliance.hr.doctype.employee_profile_change_request.employee_profile_change_request.approve_profile_change_request";
const REJECT_METHOD =
	"indian_hrms_compliance.hr.doctype.employee_profile_change_request.employee_profile_change_request.reject_profile_change_request";

frappe.ui.form.on(PCR_DOCTYPE, {
	refresh(frm) {
		render_indicator(frm);
		if (frm.is_new()) return;

		if (frm.doc.status === "Submitted") {
			frm.add_custom_button(
				__("Approve & Apply"),
				() => approve(frm),
				__("Actions")
			).addClass("btn-primary");
			frm.add_custom_button(__("Reject"), () => reject(frm), __("Actions")).addClass("btn-danger");
		}

		if (frm.doc.status === "Approved" && frm.doc.employee) {
			frm.add_custom_button(__("Open Employee"), () =>
				frappe.set_route("Form", "Employee", frm.doc.employee)
			);
		}
	},
});

function render_indicator(frm) {
	const map = {
		Submitted: "orange",
		Approved: "green",
		Rejected: "red",
		Withdrawn: "gray",
	};
	if (frm.doc.status && map[frm.doc.status]) {
		frm.page.set_indicator(__(frm.doc.status), map[frm.doc.status]);
	}
}

function approve(frm) {
	frappe.confirm(
		__("Apply these {0} change(s) to Employee {1}?", [
			(frm.doc.changes || []).length,
			frm.doc.employee_name || frm.doc.employee,
		]),
		() => {
			frappe.dom.freeze(__("Applying..."));
			frappe
				.call({ method: APPROVE_METHOD, args: { name: frm.doc.name } })
				.then((r) => {
					frappe.dom.unfreeze();
					if (!r.message) return;
					frappe.show_alert({
						message: __("Approved. Fields updated: {0}", [
							(r.message.applied_fields || []).join(", ") || __("none"),
						]),
						indicator: "green",
					});
					frm.reload_doc();
				})
				.catch(() => frappe.dom.unfreeze());
		}
	);
}

function reject(frm) {
	frappe.prompt(
		[
			{
				fieldname: "comment",
				fieldtype: "Small Text",
				label: __("Reason"),
				reqd: 1,
				description: __("Shared with the employee. Be specific."),
			},
		],
		({ comment }) => {
			frappe.call({ method: REJECT_METHOD, args: { name: frm.doc.name, comment } }).then((r) => {
				if (!r.message) return;
				frm.reload_doc();
			});
		},
		__("Reject Request"),
		__("Reject")
	);
}
