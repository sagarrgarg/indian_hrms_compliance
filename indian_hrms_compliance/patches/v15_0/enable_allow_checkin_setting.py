import frappe


def execute():
	# `allow_employee_checkin_from_mobile_app` used to live on HR Settings but is
	# now configured per Shift Type. On a fresh install the field no longer
	# exists, so guard before touching it (the per-shift seed runs separately).
	meta = frappe.get_meta("HR Settings")
	if not meta.get_field("allow_employee_checkin_from_mobile_app"):
		return

	settings = frappe.get_single("HR Settings")
	settings.allow_employee_checkin_from_mobile_app = 1
	settings.flags.ignore_mandatory = True
	settings.flags.ignore_permissions = True
	settings.save()
