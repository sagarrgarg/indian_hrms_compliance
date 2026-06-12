// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt
//
// List view of Employee Onboarding Application.
//
// Frappe loads `<doctype>_list.js` for the list page and `<doctype>.js` for the
// form page — separately. The list-view button must therefore live HERE, not
// in the form JS.

const APP_DOCTYPE = "Employee Onboarding Application";
const INVITE_FULL_METHOD =
	"indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application.generate_invite_link_full";
const RESEND_METHOD =
	"indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application.resend_invite_link";
const HR_ROLES = ["HR Manager", "HR User", "System Manager"];

function user_is_hr() {
	const roles = frappe.user_roles || [];
	return roles.some((r) => HR_ROLES.includes(r));
}

frappe.listview_settings[APP_DOCTYPE] = {
	add_fields: ["status", "submitted_on", "target_company", "target_designation"],
	get_indicator(doc) {
		const map = {
			Draft: ["Draft", "gray", "status,=,Draft"],
			"Pending Verification": [__("Pending"), "orange", "status,=,Pending Verification"],
			Verified: [__("Verified"), "blue", "status,=,Verified"],
			Converted: [__("Converted"), "green", "status,=,Converted"],
			Rejected: [__("Rejected"), "red", "status,=,Rejected"],
		};
		return map[doc.status];
	},
	onload(listview) {
		if (!user_is_hr()) return;
		listview.page
			.add_inner_button(__("Generate Invite Link"), () => open_new_candidate_invite_dialog())
			.addClass("btn-primary");
	},
};

function open_new_candidate_invite_dialog() {
	const d = new frappe.ui.Dialog({
		title: __("Invite a Candidate to Onboard"),
		size: "large",
		fields: [
			{ fieldtype: "Section Break", label: __("Candidate") },
			{ fieldname: "first_name", fieldtype: "Data", label: __("First Name"), reqd: 1 },
			{ fieldname: "middle_name", fieldtype: "Data", label: __("Middle Name") },
			{ fieldname: "last_name", fieldtype: "Data", label: __("Last Name") },
			{
				fieldname: "personal_email",
				fieldtype: "Data",
				label: __("Candidate Email"),
				options: "Email",
				reqd: 1,
				description: __("The link will be emailed here. This becomes their user login on conversion."),
			},

			{ fieldtype: "Section Break", label: __("Role (locked into the invite — candidate can't change it)") },
			{
				fieldname: "target_company",
				fieldtype: "Link",
				label: __("Target Company"),
				options: "Company",
				reqd: 1,
			},
			{
				fieldname: "target_designation",
				fieldtype: "Link",
				label: __("Target Designation"),
				options: "Designation",
				reqd: 1,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "employment_type",
				fieldtype: "Link",
				label: __("Employment Type"),
				options: "Employment Type",
			},
			{
				fieldname: "validity_days",
				fieldtype: "Int",
				label: __("Valid for (days)"),
				default: 30,
				description: __("Leave blank to use the HR Settings default."),
			},

			{ fieldtype: "Section Break", label: __("Offer Letter") },
			{
				fieldname: "offer_letter",
				fieldtype: "Attach",
				label: __("Attach Offer Letter (PDF)"),
				description: __(
					"Candidate downloads this from the onboarding form (token-protected), signs it, and uploads the signed copy — required before they can submit."
				),
			},

			{ fieldtype: "Section Break" },
			{
				fieldname: "send_email",
				fieldtype: "Check",
				label: __("Email the link to the candidate now"),
				default: 1,
			},
		],
		primary_action_label: __("Generate Link"),
		primary_action(values) {
			frappe.dom.freeze(__("Building invite link..."));
			frappe
				.call({ method: INVITE_FULL_METHOD, args: values })
				.then((r) => {
					frappe.dom.unfreeze();
					if (!r.message) return;
					d.hide();
					show_link_dialog(r.message);
					if (r.message.sent) {
						frappe.show_alert({
							message: __("Invite email queued to {0}.", [r.message.email]),
							indicator: "green",
						});
					}
				})
				.catch(() => frappe.dom.unfreeze());
		},
	});
	d.show();
}

function show_link_dialog(payload) {
	const safe_url = frappe.utils.escape_html(payload.url);
	const expiry = frappe.utils.escape_html(payload.expires_on || __("never"));
	const d = new frappe.ui.Dialog({
		title: __("Invite Link"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "html",
				options: `
					<div style="margin-bottom:8px;">${__("Share this link with the candidate. It is valid through")} <b>${expiry}</b>.</div>
					<div id="onboard-invite-url" style="word-break:break-all;padding:10px;background:#f4f5f6;border-radius:6px;font-family:monospace;font-size:12px;">${safe_url}</div>
				`,
			},
		],
		primary_action_label: __("Copy Link"),
		primary_action() {
			navigator.clipboard
				.writeText(payload.url)
				.then(() => frappe.show_alert({ message: __("Link copied to clipboard."), indicator: "green" }))
				.catch(() =>
					frappe.show_alert({ message: __("Copy failed — select the link manually."), indicator: "orange" })
				);
		},
		secondary_action_label: __("Email it Now"),
		secondary_action() {
			frappe.call({ method: RESEND_METHOD, args: { email: payload.email, validity_days: payload.validity_days } }).then(
				(r) => {
					if (!r.message) return;
					frappe.show_alert({ message: __("Email queued to {0}.", [r.message.email]), indicator: "green" });
					d.hide();
				}
			);
		},
	});
	d.show();
}
