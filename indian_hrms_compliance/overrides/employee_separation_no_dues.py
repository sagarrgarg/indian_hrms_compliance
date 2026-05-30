# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Phase 4 doc_event additions to Employee Separation.

Separated from hr.doctype.employee_separation.employee_separation so the
core controller stays the original ERPNext/HRMS class (cleaner upstream
diff). All Phase 4 behavior — no-dues template cloning, ToDo routing,
submission gate — lives here as hookable callbacks.

Wired in hooks.py under doc_events["Employee Separation"].
"""

import frappe
from frappe import _


def clone_no_dues_from_template(doc, method=None):
	"""after_insert: if the Separation has a template AND the template has
	default_no_dues_items, copy them into doc.no_dues_items.

	Skipped if no_dues_items is already populated (HR-prefilled or repeat-save)."""
	if doc.get("no_dues_items"):
		return
	if not doc.employee_separation_template:
		return
	template = frappe.get_doc("Employee Separation Template", doc.employee_separation_template)
	defaults = template.get("default_no_dues_items") or []
	if not defaults:
		return

	for row in defaults:
		doc.append(
			"no_dues_items",
			{
				"clearance_area": row.clearance_area,
				"clearance_owner": row.clearance_owner,
				"description": row.description,
				"blocking": row.blocking,
				"status": "Pending",
			},
		)
	# after_insert already committed the parent; save the child rows via db_update.
	doc.save(ignore_permissions=True)


def route_no_dues_todos(doc, method=None):
	"""on_update: ensure every no_dues_item with a clearance_owner has an
	open ToDo. Idempotent — skips owners that already have an open ToDo
	for this Separation."""
	for item in doc.get("no_dues_items") or []:
		if not item.clearance_owner or item.status == "Cleared":
			continue
		existing = frappe.db.exists(
			"ToDo",
			{
				"reference_type": "Employee Separation",
				"reference_name": doc.name,
				"allocated_to": item.clearance_owner,
				"status": "Open",
				# Keep one ToDo per (separation, owner, area) so multi-area owners
				# get one ToDo per area.
				"description": ("like", f"%[{item.clearance_area}]%"),
			},
		)
		if existing:
			continue
		description = _(
			"Clear [{0}] for <a href='/app/employee-separation/{1}'>{2}</a> "
			"({3}): {4}"
		).format(
			item.clearance_area,
			doc.name,
			doc.employee_name or doc.employee,
			doc.company or "",
			item.description or "—",
		)
		try:
			frappe.get_doc(
				{
					"doctype": "ToDo",
					"allocated_to": item.clearance_owner,
					"description": description,
					"reference_type": "Employee Separation",
					"reference_name": doc.name,
					"priority": "Medium",
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"No-Dues ToDo failed: {doc.name}/{item.clearance_owner}",
				message=frappe.get_traceback(),
			)


def block_submit_if_no_dues_pending(doc, method=None):
	"""before_submit: refuse if any blocking no_dues_item is not Cleared.

	Held rows also block — HR must resolve to Cleared or unset 'blocking' explicitly."""
	pending = []
	for item in doc.get("no_dues_items") or []:
		if item.blocking and item.status != "Cleared":
			pending.append((item.clearance_area, item.clearance_owner, item.status))
	if not pending:
		return
	lines = [
		_("Row: <b>{0}</b> owner: {1} status: {2}").format(area, owner, status)
		for area, owner, status in pending
	]
	frappe.throw(
		_("Cannot complete Separation — these blocking No-Dues are not Cleared:")
		+ "<br>"
		+ "<br>".join(lines),
		title=_("No-Dues Pending"),
	)


def close_no_dues_todos_on_cleared(doc, method=None):
	"""on_update: when a no_dues_item flips to Cleared, mark its open ToDo
	as Closed. Best-effort — failures don't block the save."""
	for item in doc.get("no_dues_items") or []:
		if item.status != "Cleared":
			continue
		open_todos = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "Employee Separation",
				"reference_name": doc.name,
				"allocated_to": item.clearance_owner,
				"status": "Open",
				"description": ("like", f"%[{item.clearance_area}]%"),
			},
			pluck="name",
		)
		for name in open_todos:
			try:
				frappe.db.set_value("ToDo", name, "status", "Closed")
			except Exception:
				pass


def stamp_relieving_date_on_completion(doc, method=None):
	"""on_update: when boarding_status flips to Completed, set
	Employee.relieving_date if not already set.

	Uses the linked Resignation Request's intended_last_working_date when
	available; otherwise today."""
	before = doc.get_doc_before_save()
	prev_status = getattr(before, "boarding_status", None) if before else None
	if doc.boarding_status != "Completed" or prev_status == "Completed":
		return
	if not doc.employee:
		return
	current = frappe.db.get_value("Employee", doc.employee, "relieving_date")
	if current:
		return
	from frappe.utils import today

	# Prefer the resignation request's intended date if linked.
	rr = frappe.db.get_value(
		"Resignation Request",
		{"linked_employee_separation": doc.name, "workflow_state": "Approved"},
		"intended_last_working_date",
	)
	relieving = rr or today()
	frappe.db.set_value("Employee", doc.employee, "relieving_date", relieving, update_modified=True)
	frappe.msgprint(
		_("Set Employee {0} relieving_date = {1}").format(doc.employee, relieving)
	)
