# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""POSH Complaint strict access control.

Implements Sec 16 confidentiality spirit: complaint detail is visible
only to (a) the complainant, (b) the accused, (c) active IC members of
the complainant's Company. HR Manager / HR User do NOT have default
read access — they can produce aggregate stats via the POSH Annual
Report but cannot drill into individual complaints.

The Administrator override applies (Administrator always sees
everything); a future hardening could remove that for production.

Wired via hooks.py permission_query_conditions and has_permission.
"""

import frappe


def posh_complaint_query(user=None):
	"""permission_query_conditions hook — SQL fragment ANDed into list-
	view / report queries for POSH Complaint.

	Returns a SQL WHERE clause restricting visibility to the three
	allowed groups. Administrator is unrestricted."""
	if not user:
		user = frappe.session.user
	if user == "Administrator":
		return ""

	# Find the Employee(s) for this user.
	emp_names = frappe.get_all(
		"Employee", filters={"user_id": user}, pluck="name"
	)

	# Find the POSH IC memberships of this user. An IC member is identified
	# by their Employee → user_id, NOT by Frappe role; IC membership lives
	# on POSH IC Member rows.
	if emp_names:
		emp_in = ",".join(["%s"] * len(emp_names))
		ic_member_ics = frappe.db.sql(
			f"""
			SELECT DISTINCT m.parent
			FROM `tabPOSH IC Member` m
			WHERE m.employee IN ({emp_in})
			  AND m.is_active = 1
			""",
			tuple(emp_names),
		)
		ic_member_ics = [r[0] for r in ic_member_ics]
	else:
		ic_member_ics = []

	# Build the WHERE clause.
	clauses = []

	# (a) complainant: rows whose complainant is one of this user's Employees
	if emp_names:
		emp_list = ",".join([frappe.db.escape(e) for e in emp_names])
		clauses.append(f"`tabPOSH Complaint`.complainant IN ({emp_list})")
		# (b) accused
		clauses.append(f"`tabPOSH Complaint`.accused IN ({emp_list})")

	# (c) IC member: rows whose internal_committee is one this user serves on
	if ic_member_ics:
		ic_list = ",".join([frappe.db.escape(i) for i in ic_member_ics])
		clauses.append(f"`tabPOSH Complaint`.internal_committee IN ({ic_list})")

	if not clauses:
		# No employee + no IC membership → user sees nothing.
		return "1=0"

	return "(" + " OR ".join(clauses) + ")"


def posh_complaint_has_permission(doc, user=None, permission_type=None):
	"""has_permission hook — fine-grained doc-level check that mirrors
	the query conditions. Called by frappe.has_permission() on
	individual records."""
	if not user:
		user = frappe.session.user
	if user == "Administrator":
		return True

	emp_names = frappe.get_all("Employee", filters={"user_id": user}, pluck="name")

	if doc.complainant in emp_names or doc.accused in emp_names:
		return True

	# IC member check
	if doc.internal_committee:
		is_member = frappe.db.sql(
			"""
			SELECT 1 FROM `tabPOSH IC Member`
			WHERE parent = %s AND employee IN ({emp_in}) AND is_active = 1
			LIMIT 1
			""".format(emp_in=",".join(["%s"] * max(len(emp_names), 1)) or "''"),
			(doc.internal_committee, *(emp_names or [""])),
		)
		if is_member:
			return True

	return False
