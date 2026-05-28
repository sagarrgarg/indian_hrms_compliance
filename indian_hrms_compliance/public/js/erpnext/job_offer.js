// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

frappe.ui.form.on("Job Offer", {
	refresh(frm) {
		if (frm.doc.status !== "Accepted" || frm.doc.docstatus !== 1) return;

		// Skip if Employee already created for this applicant.
		if (!frm.doc.job_applicant) return;
		frappe.db.get_value(
			"Employee",
			{ job_applicant: frm.doc.job_applicant },
			"name",
			(r) => {
				if (r && r.name) {
					frm.add_custom_button(
						__("View Employee"),
						() => frappe.set_route("Form", "Employee", r.name),
						__("Hire"),
					);
					return;
				}
				frm.add_custom_button(
					__("Create Employee"),
					() => open_create_employee_dialog(frm),
					__("Hire"),
				);
			},
		);
	},
});

function open_create_employee_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Create Employee from Job Offer"),
		size: "large",
		fields: [
			{ fieldtype: "Section Break", label: __("From Offer") },
			{
				fieldtype: "Read Only",
				fieldname: "applicant_name",
				label: __("Applicant"),
				default: frm.doc.applicant_name,
			},
			{
				fieldtype: "Column Break",
			},
			{
				fieldtype: "Read Only",
				fieldname: "designation",
				label: __("Designation"),
				default: frm.doc.designation,
			},
			{
				fieldtype: "Read Only",
				fieldname: "company",
				label: __("Company"),
				default: frm.doc.company,
			},
			{ fieldtype: "Section Break", label: __("Required") },
			{
				fieldtype: "Date",
				fieldname: "date_of_birth",
				label: __("Date of Birth"),
				reqd: 1,
			},
			{
				fieldtype: "Select",
				fieldname: "gender",
				label: __("Gender"),
				reqd: 1,
				options: "\nMale\nFemale\nOther",
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Date",
				fieldname: "date_of_joining",
				label: __("Date of Joining"),
				reqd: 1,
				default: frm.doc.offer_date,
			},
			{
				fieldtype: "Int",
				fieldname: "probation_days",
				label: __("Probation Duration (days)"),
				default: 90,
				description: __("scheduled_confirmation_date = date_of_joining + this"),
			},
			{ fieldtype: "Section Break", label: __("Optional") },
			{
				fieldtype: "Link",
				fieldname: "reports_to",
				label: __("Reports To"),
				options: "Employee",
				get_query: () => ({ filters: { company: frm.doc.company, status: "Active" } }),
			},
			{
				fieldtype: "Link",
				fieldname: "department",
				label: __("Department"),
				options: "Department",
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Data",
				fieldname: "bank_ac_no",
				label: __("Bank A/C No"),
			},
			{
				fieldtype: "Data",
				fieldname: "ifsc_code",
				label: __("IFSC Code"),
			},
			{ fieldtype: "Section Break", label: __("Statutory") },
			{
				fieldtype: "Data",
				fieldname: "pan_number",
				label: __("PAN"),
				description: __("Format: AAAAA9999A"),
			},
			{
				fieldtype: "Data",
				fieldname: "uan_number",
				label: __("UAN (12 digits)"),
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Data",
				fieldname: "aadhaar_last_4",
				label: __("Aadhaar Last 4"),
			},
		],
		primary_action_label: __("Create Employee"),
		primary_action(values) {
			// Submit
			frappe.call({
				method: "indian_hrms_compliance.overrides.job_offer.create_employee_from_job_offer",
				args: {
					job_offer: frm.doc.name,
					additional_fields: values,
				},
				freeze: true,
				freeze_message: __("Creating Employee..."),
				callback(r) {
					if (r && r.message) {
						dialog.hide();
						frappe.show_alert(
							{
								message: __("Employee {0} created", [r.message]),
								indicator: "green",
							},
							7,
						);
						frappe.set_route("Form", "Employee", r.message);
					}
				},
			});
		},
	});
	dialog.show();
}
