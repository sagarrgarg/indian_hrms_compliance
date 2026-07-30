# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""The self-assembling reporting tree (Section H).

The whole org chart assembles from exactly two inputs — department nesting and
one head per department. `department_head` is the SEED; `reports_to` remains the
source of truth once set. We never derive live (that would fight every manual
correction); we only fill an EMPTY reports_to, and every manual line survives.

Also here: the head-resolution fallback chain (acting → head → walk parents →
most-senior-active), the `set_reports_to` head-edit endpoint with its server-side
guards, department-scoped Designation validation, and the reports_to backfill.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

_HR_ROLES = {"HR Manager", "HR User", "System Manager"}


# --------------------------------------------------------------------------- #
# Head resolution
# --------------------------------------------------------------------------- #
def _dept_field(department: str, field: str):
	return frappe.db.get_value("Department", department, field) if department else None


def _active(emp: str | None) -> bool:
	return bool(emp) and frappe.db.get_value("Employee", emp, "status") == "Active"


def _structural_head_of(department: str) -> str | None:
	"""The PERMANENT department_head of THIS department (no acting, no walk), if
	active. This is what seeds the reporting tree — acting cover is resolved
	dynamically at approval / notification time and is NEVER written into the
	permanent, never-overwritten reports_to line.
	"""
	if not department or not frappe.get_meta("Department").has_field("department_head"):
		return None
	head = _dept_field(department, "department_head")
	return head if _active(head) else None


def department_head_of(department: str) -> str | None:
	"""The ACTING-or-permanent head of THIS department (no walk), if active.

	Acting cover wins while set and within its window. Used for DISTRIBUTION and
	escalation — where the stand-in SHOULD act — never for the structural tree.
	A head/acting who is no longer active doesn't count; a dead pointer is not a head.
	"""
	if not department or not frappe.get_meta("Department").has_field("department_head"):
		return None
	row = frappe.db.get_value(
		"Department", department, ["department_head", "acting_head", "acting_until"], as_dict=True
	)
	if not row:
		return None
	acting, until = row.acting_head, row.acting_until
	if acting and (not until or getdate(until) >= getdate(today())) and _active(acting):
		return acting
	return row.department_head if _active(row.department_head) else None


def _parent_department(department: str) -> str | None:
	return _dept_field(department, "parent_department")


def _walk_heads(department: str, employee_name: str, head_fn) -> str | None:
	"""Walk up the department chain returning the first head (per head_fn) that
	isn't the employee themselves. Bounded + cycle-guarded."""
	dept = department
	seen = set()
	for _ in range(20):
		if not dept or dept in seen:
			break
		seen.add(dept)
		head = head_fn(dept)
		if head and head != employee_name:
			return head
		dept = _parent_department(dept)
	return None


def manager_for_employee(employee_name: str, department: str) -> str | None:
	"""Whose report this employee should be, for the STRUCTURAL reports_to tree:
	the permanent head of their department, or — if that seat is themselves or
	vacant — the permanent head of the nearest ancestor department. None if no
	permanent head exists up the whole chain (the integrity check then nags).
	Acting cover is deliberately NOT considered here.
	"""
	return _walk_heads(department, employee_name, _structural_head_of)


def resolve_effective_head(department: str) -> str | None:
	"""The head for DISTRIBUTION / escalation: acting → head → nearest ancestor
	head → most-senior active person in the department. Unlike reports_to
	derivation, acting cover DOES count and there's a last-resort so an
	Assign-to-Head instance always lands on someone rather than vanishing.
	"""
	head = _walk_heads(department, "__none__", department_head_of)
	if head:
		return head
	return _most_senior_active(department)


def _most_senior_active(department: str) -> str | None:
	"""Highest seniority_rank active employee in the department (tie → any).
	Only used as the distribution fallback when no head exists anywhere up-tree.
	"""
	if not department:
		return None
	has_rank = frappe.get_meta("Designation").has_field("seniority_rank")
	emps = frappe.get_all(
		"Employee",
		filters={"department": department, "status": "Active"},
		fields=["name", "designation"],
	)
	if not emps:
		return None
	if not has_rank:
		return emps[0].name
	ranked = []
	for e in emps:
		rank = frappe.db.get_value("Designation", e.designation, "seniority_rank") or 0
		ranked.append((rank, e.name))
	ranked.sort(key=lambda t: (-t[0], t[1]))
	return ranked[0][1]


# --------------------------------------------------------------------------- #
# reports_to auto-derivation (Employee validate hook)
# --------------------------------------------------------------------------- #
def _rebuild_employee_tree() -> None:
	"""Rebuild the Employee NestedSet lft/rgt after a direct reports_to write.

	`db.set_value` on the parent field bypasses `NestedSet.on_update`, so the
	tree's lft/rgt would drift and the NEXT normal Employee.save() could throw or
	compute wrong descendants. A rebuild keeps it consistent. Wrapped so a rebuild
	hiccup never fails the head-edit / propagation itself."""
	try:
		from frappe.utils.nestedset import rebuild_tree

		rebuild_tree("Employee", "reports_to")
	except Exception:
		frappe.log_error("Employee reports_to tree rebuild failed")


def _would_cycle(employee_name: str, candidate_manager: str) -> bool:
	"""Would pointing employee.reports_to at candidate create a cycle? Walk the
	candidate's own chain; if it reaches the employee, yes. NestedSet would throw
	otherwise, so this is mandatory."""
	cur = candidate_manager
	seen = set()
	for _ in range(50):
		if not cur or cur in seen:
			return False
		if cur == employee_name:
			return True
		seen.add(cur)
		cur = frappe.db.get_value("Employee", cur, "reports_to")
	return False


def derive_reports_to(doc, method=None):
	"""Employee validate: fill an EMPTY reports_to from the department tree.

	The four safety rules, all mandatory:
	  * Never overwrite — a deliberately-set reports_to is never touched.
	  * Skip self — handled by manager_for_employee.
	  * Cycle guard — before writing.
	  * Structural, not acting — manager_for_employee derives from the permanent
	    head via department_head_of, whose acting cover is resolved dynamically,
	    not written into the tree.
	"""
	if doc.reports_to or not doc.get("department"):
		return
	mgr = manager_for_employee(doc.name or "__new__", doc.department)
	if mgr and mgr != doc.name and not _would_cycle(doc.name or "__new__", mgr):
		doc.reports_to = mgr


# --------------------------------------------------------------------------- #
# Department-scoped Designation validation (Employee validate hook)
# --------------------------------------------------------------------------- #
def validate_scoped_designation(doc, method=None):
	"""If the Employee's Designation is scoped to a department, that must match
	the Employee's department. New/changed rows are blocked; legacy mismatches
	only warn (so adopting scoping never breaks existing data)."""
	if not doc.get("designation") or not frappe.get_meta("Designation").has_field("department"):
		return
	scoped = frappe.db.get_value("Designation", doc.designation, "department")
	if not scoped or scoped == doc.get("department"):
		return
	msg = _(
		"Designation '{0}' is scoped to department '{1}', which does not match this "
		"employee's department '{2}'."
	).format(doc.designation, scoped, doc.get("department") or _("(none)"))
	if doc.is_new() or (doc.has_value_changed("designation") or doc.has_value_changed("department")):
		frappe.throw(msg, title=_("Designation / Department Mismatch"))
	frappe.msgprint(msg, indicator="orange", alert=True)


# --------------------------------------------------------------------------- #
# Department validate + propagation
# --------------------------------------------------------------------------- #
def validate_department_head(doc, method=None):
	"""Head / acting head must be active employees of THIS company; an acting
	window without an acting head is meaningless."""
	if not frappe.get_meta("Department").has_field("department_head"):
		return
	if doc.get("acting_until") and not doc.get("acting_head"):
		doc.acting_until = None
	for field, label in (("department_head", _("Department Head")), ("acting_head", _("Acting Head"))):
		emp_name = doc.get(field)
		if not emp_name:
			continue
		emp = frappe.db.get_value("Employee", emp_name, ["status", "company"], as_dict=True)
		if not emp or emp.status != "Active":
			frappe.throw(_("{0} must be an active employee.").format(label))
		if doc.get("company") and emp.company and emp.company != doc.company:
			frappe.throw(_("{0} must belong to the same company as the department.").format(label))


def propagate_department_head(doc, method=None):
	"""Department on_update: when the head changes, fill an EMPTY reports_to for
	the department's own employees (never overwrite a set one) with the PERMANENT
	head — acting cover is never baked into the structural tree. Existing members
	still pointing at the OLD head are left alone: re-pointing them is a
	deliberate, per-person call (some legitimately keep the old line in a new
	role), done via the head's `set_reports_to`, not a silent mass rewrite.
	"""
	if not frappe.get_meta("Department").has_field("department_head"):
		return
	# Only act when headship actually changed — this hook runs on every save.
	if not (doc.has_value_changed("department_head") or doc.has_value_changed("acting_head")):
		return
	head = _structural_head_of(doc.name)
	if not head:
		return
	members = frappe.get_all(
		"Employee",
		filters={"department": doc.name, "status": "Active", "reports_to": ("in", ["", None])},
		pluck="name",
	)
	filled = 0
	for m in members:
		if m == head or _would_cycle(m, head):
			continue
		frappe.db.set_value("Employee", m, "reports_to", head, update_modified=False)
		filled += 1
	if filled:
		_rebuild_employee_tree()


# --------------------------------------------------------------------------- #
# Head-edit endpoint — the head keeps their own team's tree accurate
# --------------------------------------------------------------------------- #
def _caller_employee() -> str | None:
	return frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name")


def _heads_department(caller_emp: str, department: str) -> bool:
	"""Is the caller the (acting) head of this department right now?"""
	return bool(caller_emp) and department_head_of(department) == caller_emp


@frappe.whitelist()
def set_reports_to(employee: str, new_manager: str) -> dict:
	"""Let a department head re-point a member of THEIR department — without ever
	granting Employee write access (which would expose salary / statutory IDs).

	Server-side guards, all enforced:
	  1. Caller is the (acting) head of the target's department — or HR.
	  2. Target is in the caller's department (cross-dept stays HR-only).
	  3. New manager is active, same company, and inside the department or is the
	     head themselves.
	  4. Cycle guard + skip-self.
	  5. A head cannot change their OWN reports_to.
	"""
	is_hr = bool(_HR_ROLES & set(frappe.get_roles()))
	caller = _caller_employee()
	target = frappe.db.get_value(
		"Employee", employee, ["name", "department", "company", "reports_to"], as_dict=True
	)
	if not target:
		frappe.throw(_("Employee not found."))

	if not is_hr:
		if not _heads_department(caller, target.department):
			frappe.throw(
				_("Only the head of this department (or HR) can change its reporting lines."),
				frappe.PermissionError,
			)
		if employee == caller:
			frappe.throw(
				_("You cannot change your own manager — that is your department's parent head or HR."),
				frappe.PermissionError,
			)

	if new_manager:
		mgr = frappe.db.get_value(
			"Employee", new_manager, ["status", "company", "department"], as_dict=True
		)
		if not mgr or mgr.status != "Active":
			frappe.throw(_("The new manager must be an active employee."))
		if target.company and mgr.company and mgr.company != target.company:
			frappe.throw(_("The new manager must be in the same company."))
		if not is_hr:
			# A head reorganises inside their boundary; wiring to an outsider is HR's call.
			if new_manager != caller and mgr.department != target.department:
				frappe.throw(
					_("The new manager must be within your department, or yourself."),
					frappe.PermissionError,
				)
		if new_manager == employee:
			frappe.throw(_("An employee cannot report to themselves."))
		if _would_cycle(employee, new_manager):
			frappe.throw(_("That change would create a reporting cycle."))

	old = target.reports_to
	frappe.db.set_value("Employee", employee, "reports_to", new_manager or None)
	_rebuild_employee_tree()  # keep NestedSet lft/rgt consistent after the direct write
	# Audit trail on the employee timeline (Frappe versioning captures the diff).
	frappe.get_doc("Employee", employee).add_comment(
		"Info",
		_("Reporting manager changed from {0} to {1} by {2}").format(
			old or _("(none)"), new_manager or _("(none)"), caller or frappe.session.user
		),
	)
	return {"employee": employee, "reports_to": new_manager or None, "previous": old}


@frappe.whitelist()
def get_my_department() -> dict:
	"""PWA 'My Department': the caller's department, its members, and whether the
	caller may re-point them (i.e. they are its head)."""
	caller = _caller_employee()
	if not caller:
		return {"can_manage": False, "departments": []}
	is_hr = bool(_HR_ROLES & set(frappe.get_roles()))
	# Departments the caller heads (or, for HR, their own department).
	headed = []
	if frappe.get_meta("Department").has_field("department_head"):
		for d in frappe.get_all(
			"Department",
			filters={"company": frappe.db.get_value("Employee", caller, "company")},
			fields=["name", "department_name", "department_head", "acting_head", "acting_until"],
		):
			if department_head_of(d.name) == caller or is_hr:
				headed.append(d)
	out = []
	for d in headed:
		members = frappe.get_all(
			"Employee",
			filters={"department": d.name, "status": "Active"},
			fields=["name", "employee_name", "designation", "reports_to"],
			order_by="employee_name asc",
		)
		out.append(
			{
				"department": d.name,
				"label": d.department_name or d.name,
				"is_head": department_head_of(d.name) == caller,
				"members": [m for m in members if m.name != caller],
			}
		)
	return {"can_manage": bool(out), "caller": caller, "departments": out}


# --------------------------------------------------------------------------- #
# Backfill (patch entry) — fill empty reports_to across existing employees
# --------------------------------------------------------------------------- #
def backfill_reports_to() -> int:
	"""One-time, defensive, idempotent: fill empty reports_to from the department
	tree for existing active employees. Logs how many it filled. Never overwrites.
	"""
	if not frappe.get_meta("Department").has_field("department_head"):
		return 0
	rows = frappe.get_all(
		"Employee",
		filters={"status": "Active", "reports_to": ("in", ["", None]), "department": ("is", "set")},
		fields=["name", "department"],
	)
	filled = 0
	for e in rows:
		mgr = manager_for_employee(e.name, e.department)
		if mgr and mgr != e.name and not _would_cycle(e.name, mgr):
			frappe.db.set_value("Employee", e.name, "reports_to", mgr, update_modified=False)
			filled += 1
	if filled:
		_rebuild_employee_tree()
		print(f"  Backfilled reports_to for {filled} employee(s)")
	return filled
