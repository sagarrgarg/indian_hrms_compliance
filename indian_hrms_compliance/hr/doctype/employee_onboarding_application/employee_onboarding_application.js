// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Employee Onboarding Application", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (!["Converted", "Rejected"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Generate Invite Link"), () => generate_invite(frm));
		}

		if (frm.doc.status === "Pending Verification") {
			frm.add_custom_button(__("Mark Verified"), () => {
				frm.set_value("status", "Verified");
				frm.set_value("verified_by", frappe.session.user);
				frm.save();
			});
			frm.add_custom_button(__("Reject"), () => {
				frm.set_value("status", "Rejected");
				frm.save();
			}).addClass("btn-danger");
		}

		if (["Pending Verification", "Verified"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Convert to Employee"), () => {
				frappe.route_options = { application: frm.doc.name };
				frappe.set_route("new-employee-setup");
			}).addClass("btn-primary");
		}

		if (frm.doc.status === "Converted" && frm.doc.linked_employee) {
			frm.add_custom_button(__("Open Employee"), () =>
				frappe.set_route("Form", "Employee", frm.doc.linked_employee)
			);
		}
	},
});

function generate_invite(frm) {
	frappe.prompt(
		[{ fieldname: "email", fieldtype: "Data", label: __("Candidate Email"), options: "Email", reqd: 1 }],
		({ email }) => {
			frappe.call({
				method: "indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application.generate_invite_link",
				args: { email },
				callback: (r) => {
					if (!r.message) return;
					frappe.msgprint({
						title: __("Invite Link"),
						message: `<p>${__("Share this link with the candidate:")}</p>
							<div style="word-break:break-all;padding:8px;background:#f4f5f6;border-radius:6px;">
								<a href="${r.message.url}" target="_blank">${frappe.utils.escape_html(r.message.url)}</a>
							</div>`,
						indicator: "green",
					});
				},
			});
		},
		__("Generate Invite Link"),
		__("Generate")
	);
}
