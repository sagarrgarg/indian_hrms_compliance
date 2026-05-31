"""Install the default Leave Approval / Leave Status email templates.

Distinct, India-appropriate templates with dynamic company/employee fields and
dynamic subjects, named with a "Default" prefix to mark them as app-provided.
setup.setup_notifications only runs on fresh installs, so we upsert the records
here for existing sites, repoint HR Settings, and drop the older generically
named records.
"""

import os

import frappe


TEMPLATES = {
	"Default Leave Approval Notification": {
		"file": "leave_application/leave_approval_notification_template.html",
		"subject": "Leave Approval Request from {{ employee_name }} — {{ company }}",
		"hr_settings_field": "leave_approval_notification_template",
		"legacy_name": "Leave Approval Notification",
	},
	"Default Leave Status Notification": {
		"file": "leave_application/leave_status_notification_template.html",
		"subject": "Your Leave Application has been {{ status }} — {{ company }}",
		"hr_settings_field": "leave_status_notification_template",
		"legacy_name": "Leave Status Notification",
	},
}


def execute():
	base_path = frappe.get_app_path("indian_hrms_compliance", "hr", "doctype")

	for name, cfg in TEMPLATES.items():
		response = frappe.read_file(os.path.join(base_path, cfg["file"]))

		if frappe.db.exists("Email Template", name):
			doc = frappe.get_doc("Email Template", name)
		else:
			doc = frappe.new_doc("Email Template")
			doc.name = name

		doc.use_html = 0
		doc.subject = cfg["subject"]
		doc.response = response
		doc.save(ignore_permissions=True)

		# Point HR Settings at the default template.
		frappe.db.set_single_value("HR Settings", cfg["hr_settings_field"], name)

		# Drop the older generically named record if it is no longer referenced.
		legacy = cfg["legacy_name"]
		if frappe.db.exists("Email Template", legacy):
			try:
				frappe.delete_doc("Email Template", legacy, ignore_permissions=True)
			except frappe.LinkExistsError:
				pass
