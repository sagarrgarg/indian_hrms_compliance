# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""The Employee Accountability lens.

A computed view — never stored — of everything a person is answerable for:
KRAs they are the DRI of, departments they head, playbooks they own, open task
instances assigned to them, and how many tasks route their approval. It is the
single source the Employee form renders, the mover-handover prompt is generated
from, and the leaver No-Dues gate consults to decide whether an exit is clean.

Built defensively: fields and doctypes that later phases add (department_head,
Playbook) are read only when present, so this works the moment Phase 1 ships and
grows richer as Phases 2–3 land — no rewrite.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today


def _active_dri_kras(employee: str) -> list[dict]:
	"""Active KRAs this employee is the EFFECTIVE accountable owner of.

	Effective = they are the DRI with no live acting cover, OR they are the
	current Acting DRI. Mirrors `kra.effective_dri` so the lens and the integrity
	check never disagree about who holds a KRA today.
	"""
	from indian_hrms_compliance.hr.doctype.kra.kra import effective_dri

	has_acting = frappe.get_meta("KRA").has_field("acting_dri")
	fields = ["name", "title", "company", "dri"]
	if has_acting:
		fields += ["acting_dri", "acting_until"]
	# Candidates: any Active KRA where they are dri or acting_dri.
	ors = [{"dri": employee}]
	if has_acting:
		ors = [{"dri": employee}, {"acting_dri": employee}]
	seen: dict[str, dict] = {}
	for cond in ors:
		for k in frappe.get_all(
			"KRA", filters={"status": "Active", **cond}, fields=fields
		):
			seen.setdefault(k.name, k)
	out = []
	for k in seen.values():
		# Accountable if they are the PERMANENT DRI (temporary acting cover does
		# NOT transfer ownership — the leaver gate must still block their exit) OR
		# the current effective holder (acting cover makes the stand-in
		# accountable for now). Using effective_dri alone would silently drop a
		# departing permanent owner the instant a short-window stand-in exists.
		if k.dri == employee or effective_dri(k) == employee:
			out.append({"name": k.name, "title": k.title or k.name, "company": k.company})
	return out


def _headed_departments(employee: str) -> list[dict]:
	"""Departments this employee heads — only when Phase 3 added the field."""
	if not frappe.get_meta("Department").has_field("department_head"):
		return []
	rows = frappe.get_all(
		"Department",
		filters={"department_head": employee},
		fields=["name", "department_name", "company"],
	)
	return [
		{"name": d.name, "label": d.department_name or d.name, "company": d.company} for d in rows
	]


def _owned_playbooks(employee: str) -> list[dict]:
	"""Playbooks this employee owns — only when Phase 2 added the doctype."""
	if not frappe.db.exists("DocType", "Playbook"):
		return []
	rows = frappe.get_all(
		"Playbook",
		filters={"dri": employee, "status": ("!=", "Retired")},
		fields=["name", "title", "company"],
	)
	return [{"name": p.name, "title": p.title or p.name, "company": p.company} for p in rows]


def _open_task_instances(employee: str) -> int:
	"""Open Task Instances assigned to this employee (work still owed)."""
	return frappe.db.count(
		"Goal",
		{"goal_type": "Task Instance", "employee": employee, "status": ("in", ["Pending", "In Progress"])},
	)


def _approver_of(employee: str) -> int:
	"""Active task instances awaiting THIS person's approval decision."""
	user = frappe.db.get_value("Employee", employee, "user_id")
	if not user:
		return 0
	return frappe.db.count(
		"Goal",
		{
			"goal_type": "Task Instance",
			"approver_user": user,
			"status": "In Progress",
			"submitted_at": ("is", "set"),
		},
	)


@frappe.whitelist()
def get_accountability(employee: str | None = None) -> dict:
	"""The full accountability lens for one employee.

	Defaults to the caller's own Employee. HR / a reporting manager may pass any
	employee; a plain employee may only view their own (handover is HR-driven,
	but a person seeing their own load is harmless and useful).
	"""
	if not employee:
		employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not employee:
		frappe.throw(_("No employee record to compute accountability for."))

	roles = set(frappe.get_roles())
	is_hr = bool({"HR Manager", "HR User", "System Manager"} & roles)
	if not is_hr:
		own = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		# A reporting manager may look at a direct/indirect report's load too.
		if employee != own and not _is_in_reporting_chain(employee, own):
			frappe.throw(
				_("You can only view your own accountability."), frappe.PermissionError
			)

	dri_kras = _active_dri_kras(employee)
	headed = _headed_departments(employee)
	playbooks = _owned_playbooks(employee)
	open_instances = _open_task_instances(employee)
	approver_of = _approver_of(employee)

	# The leaver gate's signal: an exit is clean only when nobody is left holding
	# the bag — no active-KRA ownership, no headship, no open assigned work. This
	# mirrors the blueprint's No-Dues gate exactly. `approver_of` is deliberately
	# NOT a hard block: reassigning approver routing is the mover/leaver HANDOVER
	# prompt's job (Phase 3b), and hard-blocking an exit on it would trap people
	# behind other employees' unsubmitted work. It's surfaced for that handover.
	blocking = bool(dri_kras) or bool(headed) or open_instances > 0
	return {
		"employee": employee,
		"employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
		"dri_kras": dri_kras,
		"headed_departments": headed,
		"owned_playbooks": playbooks,
		"open_task_instances": open_instances,
		"approver_of": approver_of,
		"is_clear": not blocking,
		"blocking_reasons": _blocking_reasons(dri_kras, headed, open_instances),
	}


def _blocking_reasons(dri_kras, headed, open_instances) -> list[str]:
	reasons = []
	if dri_kras:
		reasons.append(_("DRI of {0} active KRA(s)").format(len(dri_kras)))
	if headed:
		reasons.append(_("Head of {0} department(s)").format(len(headed)))
	if open_instances:
		reasons.append(_("{0} open task instance(s)").format(open_instances))
	return reasons


def _is_in_reporting_chain(employee: str, manager: str) -> bool:
	"""Is `manager` somewhere up `employee`'s reports_to chain? Bounded walk."""
	if not manager:
		return False
	seen = set()
	cur = employee
	for _ in range(20):  # cycle/depth guard
		if not cur or cur in seen:
			return False
		seen.add(cur)
		rt = frappe.db.get_value("Employee", cur, "reports_to")
		if rt == manager:
			return True
		cur = rt
	return False
