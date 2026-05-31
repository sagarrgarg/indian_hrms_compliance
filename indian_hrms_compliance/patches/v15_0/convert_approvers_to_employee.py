import frappe

APPROVER_FIELDS = ("expense_approver", "leave_approver", "shift_request_approver")


def execute():
	"""Convert Employee.{expense,leave,shift_request}_approver from Link->User to
	Link->Employee, and migrate existing User-email values to the matching Employee
	(preferring an Active employee in the same company)."""

	# 1. Repoint the custom fields at Employee.
	for fieldname in APPROVER_FIELDS:
		cf = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": fieldname})
		if cf:
			frappe.db.set_value("Custom Field", cf, "options", "Employee", update_modified=False)

	# 2. Migrate stored values from User -> Employee.
	rows = frappe.get_all(
		"Employee",
		fields=["name", "company", *APPROVER_FIELDS],
	)
	unmapped = []
	for row in rows:
		updates = {}
		for fieldname in APPROVER_FIELDS:
			value = row.get(fieldname)
			if not value:
				continue
			# Idempotent: already an Employee (re-run or fresh data).
			if frappe.db.exists("Employee", value):
				continue
			employee = _user_to_employee(value, row.company)
			updates[fieldname] = employee
			if not employee:
				unmapped.append((row.name, fieldname, value))
		if updates:
			frappe.db.set_value("Employee", row.name, updates, update_modified=False)

	if unmapped:
		# Approver users with no Employee record were cleared; surface them in the log.
		print(
			"convert_approvers_to_employee: cleared unmappable approvers (no Employee for user): "
			+ ", ".join(f"{e}.{f}={v}" for e, f, v in unmapped)
		)

	frappe.clear_cache(doctype="Employee")


def _user_to_employee(user, company):
	"""Best-effort User -> Employee, preferring the same company and Active status."""
	for filters in (
		{"user_id": user, "company": company, "status": "Active"},
		{"user_id": user, "company": company},
		{"user_id": user, "status": "Active"},
		{"user_id": user},
	):
		employee = frappe.db.get_value("Employee", filters)
		if employee:
			return employee
	return None
