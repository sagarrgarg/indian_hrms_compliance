// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Onboarding", {
	setup: function (frm) {
		frm.set_query("job_applicant", function () {
			return {
				filters: {
					status: "Accepted",
				},
			};
		});

		frm.set_query("job_offer", function () {
			return {
				filters: {
					job_applicant: frm.doc.job_applicant,
					docstatus: 1,
				},
			};
		});
	},

	refresh: function (frm) {
		if (frm.doc.employee) {
			frm.add_custom_button(
				__("Employee"),
				function () {
					frappe.set_route("Form", "Employee", frm.doc.employee);
				},
				__("View"),
			);
			frm.trigger("render_setup_status");
		}
		if (frm.doc.project) {
			frm.add_custom_button(
				__("Project"),
				function () {
					frappe.set_route("Form", "Project", frm.doc.project);
				},
				__("View"),
			);
			frm.add_custom_button(
				__("Task"),
				function () {
					frappe.set_route("List", "Task", { project: frm.doc.project });
				},
				__("View"),
			);
		}
		if (!frm.doc.employee && frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("Employee"),
				function () {
					frappe.model.open_mapped_doc({
						method: "indian_hrms_compliance.hr.doctype.employee_onboarding.employee_onboarding.make_employee",
						frm: frm,
					});
				},
				__("Create"),
			);
			frm.page.set_inner_btn_group_as_primary(__("Create"));
		}
		if (
			frm.doc.docstatus === 1 &&
			(frm.doc.boarding_status === "Pending" || frm.doc.boarding_status === "In Process")
		) {
			frm.add_custom_button(__("Mark as Completed"), function () {
				frm.trigger("mark_as_completed");
			});
		}
	},

	employee_onboarding_template: function (frm) {
		frm.set_value("activities", "");
		if (frm.doc.employee_onboarding_template) {
			frappe.call({
				method: "indian_hrms_compliance.controllers.employee_boarding_controller.get_onboarding_details",
				args: {
					parent: frm.doc.employee_onboarding_template,
					parenttype: "Employee Onboarding Template",
				},
				callback: function (r) {
					if (r.message) {
						r.message.forEach((d) => {
							frm.add_child("activities", d);
						});
						refresh_field("activities");
					}
				},
			});
		}
	},

	job_applicant: function (frm) {
		if (frm.doc.job_applicant) {
			frappe.db.get_value(
				"Employee",
				{ job_applicant: frm.doc.job_applicant },
				"name",
				(r) => {
					if (r.name) {
						frm.set_value("employee", r.name);
					} else {
						frm.set_value("employee", "");
					}
				},
			);
		} else {
			frm.set_value("employee", "");
		}
	},

	render_setup_status(frm) {
		if (!frm.doc.employee) return;
		frappe.call({
			method: "indian_hrms_compliance.overrides.employee_master.get_employee_setup_status",
			args: { employee: frm.doc.employee },
			callback: function (r) {
				if (!r.message || !r.message.items) return;
				const rows = r.message.items
					.map((item) => {
						const icon = item.done
							? '<span style="color:var(--green-600)">&#10003;</span>'
							: '<span style="color:var(--gray-500)">&#9675;</span>';
						const action = item.done ? __("View") : __("Set up");
						const route = encodeURIComponent(JSON.stringify(item.route));
						return `<div style="display:flex;align-items:center;gap:8px;padding:4px 0">
								${icon}
								<span style="flex:1">${frappe.utils.escape_html(item.label)}</span>
								<a href="#" data-route="${route}" class="ihc-setup-link">${action}</a>
							</div>`;
					})
					.join("");
				const $section = frm.dashboard.add_section(
					`<div class="ihc-setup-status">${rows}</div>`,
					__("HR Setup Status"),
				);
				$section.find(".ihc-setup-link").on("click", function (e) {
					e.preventDefault();
					const route = JSON.parse(decodeURIComponent($(this).attr("data-route")));
					frappe.set_route(...route);
				});
			},
		});
	},

	mark_as_completed(frm) {
		frm.call({
			method: "mark_onboarding_as_completed",
			doc: frm.doc,
			freeze: true,
			freeze_message: __("Completing onboarding"),
		}).then((r) => {
			frm.refresh();
		});
	},
});
