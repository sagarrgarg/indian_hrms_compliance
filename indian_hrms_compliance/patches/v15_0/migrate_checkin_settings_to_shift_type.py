import frappe
from frappe.utils import cint


def execute():
	"""Mobile check-in + geolocation tracking moved from HR Settings (global) to
	per Shift Type. Seed every Shift Type from the old global values, then drop
	the now-orphaned HR Settings singles rows so the stale globals don't linger.
	"""
	# Read straight from tabSingles with raw SQL — the fields are gone from HR
	# Settings' meta (so get_single_value errors) and tabSingles has no `modified`
	# column (so get_value's default ORDER BY errors), but the old values still
	# sit there until we clean them below.
	def _old_global(field):
		rows = frappe.db.sql(
			"select value from tabSingles where doctype = %s and field = %s",
			("HR Settings", field),
		)
		return rows[0][0] if rows else None

	old_checkin = _old_global("allow_employee_checkin_from_mobile_app")
	old_geolocation = _old_global("allow_geolocation_tracking")

	# Fall back to the historical field defaults when the singles row is absent.
	checkin = 1 if old_checkin is None else cint(old_checkin)
	geolocation = cint(old_geolocation)  # historical default 0

	for name in frappe.get_all("Shift Type", pluck="name"):
		frappe.db.set_value(
			"Shift Type",
			name,
			{
				"allow_employee_checkin_from_mobile_app": checkin,
				"allow_geolocation_tracking": geolocation,
			},
			update_modified=False,
		)

	frappe.db.delete(
		"Singles",
		{
			"doctype": "HR Settings",
			"field": ["in", ["allow_employee_checkin_from_mobile_app", "allow_geolocation_tracking"]],
		},
	)
