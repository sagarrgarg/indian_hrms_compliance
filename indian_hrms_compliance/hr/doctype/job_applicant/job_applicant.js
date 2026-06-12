// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

// For license information, please see license.txt

// for communication
cur_frm.email_field = "email_id";

frappe.ui.form.on("Job Applicant", {
	refresh: function (frm) {
		frm.set_query("job_title", function () {
			return {
				filters: {
					status: "Open",
				},
			};
		});
		frm.events.create_custom_buttons(frm);
		frm.events.make_dashboard(frm);
	},

	create_custom_buttons: function (frm) {
		if (!frm.doc.__islocal && frm.doc.status !== "Rejected" && frm.doc.status !== "Accepted") {
			frm.add_custom_button(
				__("Interview"),
				function () {
					frm.events.create_dialog(frm);
				},
				__("Create"),
			);
		}

		if (!frm.doc.__islocal && frm.doc.status == "Accepted") {
			if (frm.doc.__onload && frm.doc.__onload.job_offer) {
				$('[data-doctype="Employee Onboarding"]').find("button").show();
				$('[data-doctype="Job Offer"]').find("button").hide();
				frm.add_custom_button(
					__("Job Offer"),
					function () {
						frappe.set_route("Form", "Job Offer", frm.doc.__onload.job_offer);
					},
					__("View"),
				);
			} else {
				$('[data-doctype="Employee Onboarding"]').find("button").hide();
				$('[data-doctype="Job Offer"]').find("button").show();
				frm.add_custom_button(
					__("Job Offer"),
					function () {
						frappe.route_options = {
							job_applicant: frm.doc.name,
							applicant_name: frm.doc.applicant_name,
							designation: frm.doc.job_opening || frm.doc.designation,
						};
						frappe.new_doc("Job Offer");
					},
					__("Create"),
				);
			}

			// Send the candidate a self-service onboarding invite link. Reuses
			// the same signed-token flow as the Employee Onboarding Application
			// list view — the role/company/designation get baked into the token.
			frm.add_custom_button(
				__("Send Onboarding Invite"),
				function () {
					frm.events.send_onboarding_invite(frm);
				},
				__("Create"),
			).addClass("btn-primary");
		}
	},

	send_onboarding_invite: function (frm) {
		const PREFILL =
			"indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application.get_applicant_onboarding_prefill";
		const GENERATE =
			"indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application.generate_invite_link_full";

		frappe.call({ method: PREFILL, args: { job_applicant: frm.doc.name } }).then((r) => {
			const p = r.message;
			if (!p) return;

			if (p.existing_application) {
				frappe.msgprint({
					title: __("Heads up"),
					indicator: "orange",
					message: __(
						"An onboarding application from this email already exists ({0}). Sending a new invite is fine, but check it isn't a duplicate.",
						[p.existing_application],
					),
				});
			}

			const d = new frappe.ui.Dialog({
				title: __("Send Onboarding Invite"),
				size: "large",
				fields: [
					{ fieldtype: "Section Break", label: __("Candidate") },
					{ fieldname: "first_name", fieldtype: "Data", label: __("First Name"), reqd: 1, default: p.first_name },
					{ fieldname: "last_name", fieldtype: "Data", label: __("Last Name"), default: p.last_name },
					{
						fieldname: "personal_email",
						fieldtype: "Data",
						label: __("Candidate Email"),
						options: "Email",
						reqd: 1,
						default: p.personal_email,
						description: __("The link is emailed here; it becomes their login on conversion."),
					},
					{ fieldtype: "Section Break", label: __("Role (locked into the invite)") },
					{
						fieldname: "target_company",
						fieldtype: "Link",
						label: __("Target Company"),
						options: "Company",
						reqd: 1,
						default: p.target_company,
					},
					{
						fieldname: "target_designation",
						fieldtype: "Link",
						label: __("Target Designation"),
						options: "Designation",
						reqd: 1,
						default: p.target_designation,
					},
					{ fieldtype: "Column Break" },
					{
						fieldname: "employment_type",
						fieldtype: "Link",
						label: __("Employment Type"),
						options: "Employment Type",
						default: p.employment_type,
					},
					{
						fieldname: "validity_days",
						fieldtype: "Int",
						label: __("Valid for (days)"),
						default: 30,
					},
					{ fieldtype: "Section Break", label: __("Offer Letter") },
					{
						fieldname: "offer_letter",
						fieldtype: "Attach",
						label: __("Attach Offer Letter (PDF)"),
						description: __(
							"Candidate downloads this from the onboarding form (token-protected), signs it, and uploads the signed copy — required before they can submit.",
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
					frappe.dom.freeze(__("Building invite link…"));
					frappe
						.call({ method: GENERATE, args: values })
						.then((res) => {
							frappe.dom.unfreeze();
							if (!res.message) return;
							d.hide();
							frm.events.show_invite_link(res.message);
						})
						.catch(() => frappe.dom.unfreeze());
				},
			});
			d.show();
		});
	},

	show_invite_link: function (m) {
		const EMAIL_LINK =
			"indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application.email_invite_link";
		const safe = frappe.utils.escape_html(m.url);
		const expiry = frappe.utils.escape_html(m.expires_on || __("never"));
		const dialog = new frappe.ui.Dialog({
			title: __("Onboarding Invite Link"),
			fields: [
				{
					fieldtype: "HTML",
					options: `<p>${__("Valid through")} <b>${expiry}</b>.${
						m.sent ? " " + __("Already emailed to {0}.", [frappe.utils.escape_html(m.email)]) : ""
					}</p>
					<div style="word-break:break-all;padding:10px;background:#f4f5f6;border-radius:6px;font-family:monospace;font-size:12px;">${safe}</div>
					<p style="margin-top:8px;font-size:12px;color:#777;">${__("Copy the link to share manually, or email it to the candidate.")}</p>`,
				},
			],
			primary_action_label: __("Copy Link"),
			primary_action() {
				navigator.clipboard
					.writeText(m.url)
					.then(() => frappe.show_alert({ message: __("Link copied to clipboard."), indicator: "green" }))
					.catch(() => frappe.show_alert({ message: __("Copy failed — select it manually."), indicator: "orange" }));
			},
			secondary_action_label: __("Email to Candidate"),
			secondary_action() {
				frappe
					.call({
						method: EMAIL_LINK,
						args: { email: m.email, url: m.url, expires_on: m.expires_on },
					})
					.then((r) => {
						if (!r.message) return;
						frappe.show_alert({
							message: __("Emailed to {0}.", [r.message.email]),
							indicator: "green",
						});
					});
			},
		});
		dialog.show();
	},

	make_dashboard: function (frm) {
		frappe.call({
			method: "indian_hrms_compliance.hr.doctype.job_applicant.job_applicant.get_interview_details",
			args: {
				job_applicant: frm.doc.name,
			},
			callback: function (r) {
				if (r.message) {
					$("div").remove(".form-dashboard-section.custom");
					frm.dashboard.add_section(
						frappe.render_template("job_applicant_dashboard", {
							data: r.message.interviews,
							number_of_stars: r.message.stars,
						}),
						__("Interview Summary"),
					);
				}
			},
		});
	},

	create_dialog: function (frm) {
		let d = new frappe.ui.Dialog({
			title: "Enter Interview Round",
			fields: [
				{
					label: "Interview Round",
					fieldname: "interview_round",
					fieldtype: "Link",
					options: "Interview Round",
				},
			],
			primary_action_label: __("Create Interview"),
			primary_action(values) {
				frm.events.create_interview(frm, values);
				d.hide();
			},
		});
		d.show();
	},

	create_interview: function (frm, values) {
		frappe.call({
			method: "indian_hrms_compliance.hr.doctype.job_applicant.job_applicant.create_interview",
			args: {
				doc: frm.doc,
				interview_round: values.interview_round,
			},
			callback: function (r) {
				var doclist = frappe.model.sync(r.message);
				frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
			},
		});
	},
});
