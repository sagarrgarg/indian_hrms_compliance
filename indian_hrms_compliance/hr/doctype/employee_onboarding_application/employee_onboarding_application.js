// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

const APP_DOCTYPE = "Employee Onboarding Application";
const INVITE_METHOD =
	"indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application.generate_invite_link";
const RESEND_METHOD =
	"indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application.resend_invite_link";

frappe.ui.form.on(APP_DOCTYPE, {
	refresh(frm) {
		render_status_indicator(frm);
		if (frm.is_new()) return;

		if (!["Converted", "Rejected"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Generate Invite Link"), () => generate_invite(frm.doc.personal_email));
			if (frm.doc.personal_email) {
				frm.add_custom_button(__("Resend Invite by Email"), () => resend_invite(frm.doc.personal_email));
			}
		}

		if (frm.doc.status === "Pending Verification") {
			frm.add_custom_button(__("Mark Verified"), () => mark_verified(frm)).addClass("btn-primary");
			frm.add_custom_button(__("Reject"), () => reject(frm)).addClass("btn-danger");
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

		render_consent_panel(frm);
		render_checklist_progress(frm);
	},

	status(frm) {
		// Clear rejection_reason if user toggles away from Rejected.
		if (frm.doc.status !== "Rejected" && frm.doc.rejection_reason) {
			frm.set_value("rejection_reason", "");
		}
	},

	same_as_current_address(frm) {
		// Mirror current -> permanent when ticked (server also enforces on save).
		if (frm.doc.same_as_current_address) {
			frm.set_value("permanent_address", frm.doc.current_address || "");
		}
	},

	current_address(frm) {
		if (frm.doc.same_as_current_address) {
			frm.set_value("permanent_address", frm.doc.current_address || "");
		}
	},
});

function render_status_indicator(frm) {
	const map = {
		Draft: "gray",
		"Pending Verification": "orange",
		Verified: "blue",
		Converted: "green",
		Rejected: "red",
	};
	if (frm.doc.status && map[frm.doc.status]) {
		frm.page.set_indicator(__(frm.doc.status), map[frm.doc.status]);
	}
}

function render_consent_panel(frm) {
	if (!frm.doc.dpdp_consent) return;
	const ts = frm.doc.consent_timestamp ? frappe.datetime.str_to_user(frm.doc.consent_timestamp) : __("not captured");
	const ip = frappe.utils.escape_html(frm.doc.consent_ip || __("not captured"));
	const ver = frappe.utils.escape_html(frm.doc.consent_text_version || "1.0");
	frm.dashboard.add_comment(
		`<span style="color:#0d6e3f;">${__("DPDP consent captured")} — v${ver}, ${ts}, IP ${ip}</span>`,
		"green",
		true
	);
}

function render_checklist_progress(frm) {
	if (["Converted", "Rejected"].includes(frm.doc.status)) return;
	const items = [
		["pan_verified", __("PAN")],
		["aadhaar_verified", __("Aadhaar")],
		["bank_verified", __("Bank")],
		["photo_verified", __("Photo")],
	];
	const done = items.filter(([f]) => frm.doc[f]).length;
	const total = items.length;
	if (done === total) {
		frm.dashboard.add_comment(__("All verification checks ticked — ready to mark Verified."), "green", true);
	} else if (done > 0) {
		frm.dashboard.add_comment(
			__("Verification checklist: {0}/{1} ticked.", [done, total]),
			"orange",
			true
		);
	}
}

function mark_verified(frm) {
	frappe.confirm(__("Mark this application as Verified?"), () => {
		frm.set_value("status", "Verified");
		frm.set_value("verified_by", frappe.session.user);
		frm.set_value("verified_on", frappe.datetime.now_datetime());
		frm.save();
	});
}

function reject(frm) {
	frappe.prompt(
		[
			{
				fieldname: "rejection_reason",
				fieldtype: "Small Text",
				label: __("Rejection Reason"),
				reqd: 1,
				description: __("This is shared with the candidate in the rejection email — be specific but courteous."),
			},
		],
		({ rejection_reason }) => {
			frm.set_value("rejection_reason", rejection_reason);
			frm.set_value("status", "Rejected");
			frm.save();
		},
		__("Reject Application"),
		__("Reject")
	);
}

function generate_invite(default_email) {
	frappe.prompt(
		[
			{
				fieldname: "email",
				fieldtype: "Data",
				label: __("Candidate Email"),
				options: "Email",
				reqd: 1,
				default: default_email,
			},
			{
				fieldname: "validity_days",
				fieldtype: "Int",
				label: __("Valid for (days)"),
				default: 30,
				description: __("Leave blank to use the HR Settings default."),
			},
		],
		({ email, validity_days }) => {
			frappe.call({ method: INVITE_METHOD, args: { email, validity_days } }).then((r) => {
				if (!r.message) return;
				show_link_dialog(r.message);
			});
		},
		__("Generate Invite Link"),
		__("Generate")
	);
}

function resend_invite(default_email) {
	frappe.prompt(
		[
			{
				fieldname: "email",
				fieldtype: "Data",
				label: __("Candidate Email"),
				options: "Email",
				reqd: 1,
				default: default_email,
			},
			{
				fieldname: "validity_days",
				fieldtype: "Int",
				label: __("Valid for (days)"),
				default: 30,
			},
		],
		({ email, validity_days }) => {
			frappe.call({ method: RESEND_METHOD, args: { email, validity_days } }).then((r) => {
				if (!r.message) return;
				frappe.show_alert({
					message: __("Invite email queued to {0} — valid through {1}.", [
						r.message.email,
						r.message.expires_on,
					]),
					indicator: "green",
				});
			});
		},
		__("Resend Invite by Email"),
		__("Send")
	);
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

// NOTE: List-view button + its dialog live in employee_onboarding_application_list.js
// — Frappe loads `<doctype>_list.js` separately from the form JS, so the list
// view never sees code declared here.
