# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from pypika import CustomFunction

import frappe
from frappe import _
from frappe.query_builder.functions import Avg
from frappe.utils import cint, flt
from frappe.utils.nestedset import NestedSet

from indian_hrms_compliance.hr.doctype.appraisal_cycle.appraisal_cycle import validate_active_appraisal_cycle
from indian_hrms_compliance.hr.utils import validate_active_employee


class Goal(NestedSet):
	nsm_parent_field = "parent_goal"

	def before_insert(self):
		if cint(self.is_group):
			self.progress = 0

	def validate(self):
		if self.appraisal_cycle:
			validate_active_appraisal_cycle(self.appraisal_cycle)

		validate_active_employee(self.employee)
		self.validate_parent_fields()
		self.validate_from_to_dates(self.start_date, self.end_date)
		self.validate_progress()
		self.set_status()
		self._guard_task_instance_governance()

	def _guard_task_instance_governance(self):
		"""Enforce the approval invariant at the DOCUMENT layer, not just the API.

		The whitelisted governance endpoints (complete/approve/reject/reopen) are
		careful — but Goal also exposes its own `update_status` / `update_progress`
		whitelists and the generic `client.set_value`, and the Employee role has a
		blanket write perm. Without this, a doer could mark their own Critical task
		'Completed' straight through those, never touching an approver, and could
		hand-write `approved_by` (Frappe does NOT enforce `read_only` server-side).

		Trusted paths set `flags.ihc_governed_write` before saving; everything else
		is treated as a raw client write and may not:
		  * create or change any approval/submission stamp, or
		  * push an approval-gated instance to 'Completed' without a real sign-off.

		Reminder back-fills use `db.set_value`, which bypasses validate entirely,
		so they are unaffected.
		"""
		if self.goal_type != "Task Instance" or self.flags.get("ihc_governed_write"):
			return

		before = self.get_doc_before_save()

		# 1. Approval/submission stamps are system-owned — never client-editable.
		stamp_fields = (
			"submitted_at",
			"submitted_by",
			"approved_by",
			"approved_at",
			"approval_notes",
		)
		for f in stamp_fields:
			if not self.meta.has_field(f):
				continue
			old = (before.get(f) if before else None) or None
			if (self.get(f) or None) != old:
				frappe.throw(
					_(
						"Approval details on a task are written by the approval workflow, "
						"not editable directly."
					),
					frappe.PermissionError,
					title=_("Not Allowed"),
				)

		# 2. Routing identity is frozen once the instance exists. Otherwise a doer
		#    could clear `task_template` (making the Completed check below think the
		#    task needs no approval) or swap it for a Routine one, or re-point
		#    `approver_user` / `approver_role` at a friendly colleague. The only
		#    legitimate writers of these are the scheduler at INSERT (before is
		#    None → exempt) and leave-cover delegation via `db.set_value` (bypasses
		#    validate entirely → exempt).
		if before:
			for f in ("task_template", "approver_user", "approver_role"):
				if not self.meta.has_field(f):
					continue
				if (self.get(f) or None) != (before.get(f) or None):
					frappe.throw(
						_("A task's template and approver routing cannot be changed directly."),
						frappe.PermissionError,
						title=_("Not Allowed"),
					)

		# 3. An approval-gated instance may not reach Completed without a sign-off.
		#    `task_template` is now proven unchanged (frozen above), so reading
		#    requires_approval from it is trustworthy.
		if self.status == "Completed" and not self.get("approved_by"):
			requires_approval = self.task_template and frappe.db.get_value(
				"HRMS Task", self.task_template, "requires_approval"
			)
			if requires_approval:
				frappe.throw(
					_(
						"This task requires approval and cannot be marked complete directly — "
						"submit it for approval instead."
					),
					frappe.PermissionError,
					title=_("Approval Required"),
				)

	def on_update(self):
		NestedSet.on_update(self)

		doc_before_save = self.get_doc_before_save()

		if doc_before_save:
			self.update_kra_in_child_goals(doc_before_save)

			if doc_before_save.parent_goal != self.parent_goal:
				# parent goal changed, update progress of old parent
				self.update_parent_progress(doc_before_save.parent_goal)

		self.update_parent_progress()
		self.update_goal_progress_in_appraisal()

	def on_trash(self):
		NestedSet.on_trash(self, allow_root_deletion=True)

	def after_delete(self):
		self.update_parent_progress()
		self.update_goal_progress_in_appraisal()

	def validate_parent_fields(self):
		if not self.parent_goal:
			return

		parent_details = frappe.db.get_value(
			"Goal", self.parent_goal, ["employee", "kra", "appraisal_cycle"], as_dict=True
		)
		if not parent_details:
			return

		if self.employee != parent_details.employee:
			frappe.throw(
				_("Goal should be owned by the same employee as its parent goal."), title=_("Not Allowed")
			)
		if self.kra != parent_details.kra:
			frappe.throw(
				_("Goal should be aligned with the same KRA as its parent goal."), title=_("Not Allowed")
			)
		if self.appraisal_cycle != parent_details.appraisal_cycle:
			frappe.throw(
				_("Goal should belong to the same Appraisal Cycle as its parent goal."),
				title=_("Not Allowed"),
			)

	def validate_progress(self):
		if flt(self.progress) > 100:
			frappe.throw(_("Goal progress percentage cannot be more than 100."))

	def set_status(self, status=None):
		if self.status in ["Archived", "Closed"]:
			return
		if flt(self.progress) == 0:
			self.status = "Pending"
		elif flt(self.progress) == 100:
			self.status = "Completed"
		elif flt(self.progress) < 100:
			self.status = "In Progress"

	def update_kra_in_child_goals(self, doc_before_save):
		"""Aligns children's KRA to parent goal's KRA if parent goal's KRA is changed"""
		if doc_before_save.kra != self.kra and self.is_group:
			Goal = frappe.qb.DocType("Goal")
			(frappe.qb.update(Goal).set(Goal.kra, self.kra).where(Goal.parent_goal == self.name)).run()

			frappe.msgprint(_("KRA updated for all child goals."), alert=True, indicator="green")

	def update_parent_progress(self, old_parent=None):
		parent_goal = old_parent or self.parent_goal

		if not parent_goal:
			return

		Goal = frappe.qb.DocType("Goal")
		avg_goal_completion = (
			frappe.qb.from_(Goal)
			.select(Avg(Goal.progress).as_("avg_goal_completion"))
			.where(
				(Goal.parent_goal == parent_goal)
				& (Goal.employee == self.employee)
				# archived goals should not contribute to progress
				& (Goal.status != "Archived")
			)
		).run()[0][0]

		parent_goal_doc = frappe.get_doc("Goal", parent_goal)
		parent_goal_doc.progress = flt(avg_goal_completion, parent_goal_doc.precision("progress"))
		parent_goal_doc.ignore_permissions = True
		parent_goal_doc.ignore_mandatory = True
		parent_goal_doc.save()

	def update_goal_progress_in_appraisal(self):
		if not self.appraisal_cycle:
			return

		appraisal = frappe.db.get_value(
			"Appraisal", {"employee": self.employee, "appraisal_cycle": self.appraisal_cycle}
		)
		if appraisal:
			appraisal = frappe.get_doc("Appraisal", appraisal)
			appraisal.set_goal_score(update=True)


@frappe.whitelist()
def get_children(doctype: str, parent: str, is_root: bool = False, **filters) -> list[dict]:
	Goal = frappe.qb.DocType(doctype)

	query = (
		frappe.qb.from_(Goal)
		.select(
			Goal.name.as_("value"),
			Goal.goal_name.as_("title"),
			Goal.is_group.as_("expandable"),
			Goal.status,
			Goal.employee,
			Goal.employee_name,
			Goal.appraisal_cycle,
			Goal.progress,
			Goal.kra,
		)
		.where(Goal.status != "Archived")
	)

	if filters.get("employee"):
		query = query.where(Goal.employee == filters.get("employee"))

	if filters.get("appraisal_cycle"):
		query = query.where(Goal.appraisal_cycle == filters.get("appraisal_cycle"))

	if filters.get("goal"):
		query = query.where(Goal.parent_goal == filters.get("goal"))
	elif parent and not is_root:
		# via expand child
		query = query.where(Goal.parent_goal == parent)
	else:
		ifnull = CustomFunction("IFNULL", ["value", "default"])
		query = query.where(ifnull(Goal.parent_goal, "") == "")

	if filters.get("date_range"):
		date_range = frappe.parse_json(filters.get("date_range"))

		query = query.where(
			(Goal.start_date.between(date_range[0], date_range[1]))
			& ((Goal.end_date.isnull()) | (Goal.end_date.between(date_range[0], date_range[1])))
		)

	goals = query.orderby(Goal.employee, Goal.kra).run(as_dict=True)
	_update_goal_completion_status(goals)

	return goals


def _update_goal_completion_status(goals: list[dict]) -> list[dict]:
	for goal in goals:
		if goal.expandable:  # group node
			total_goals = frappe.db.count("Goal", dict(parent_goal=goal.value))

			if total_goals:
				completed = frappe.db.count("Goal", {"parent_goal": goal.value, "status": "Completed"}) or 0
				# set completion status of group node
				goal["completion_count"] = _("{0} of {1} Completed").format(completed, total_goals)

	return goals


@frappe.whitelist()
def update_progress(progress: float, goal: str) -> None:
	goal = frappe.get_doc("Goal", goal)
	goal.progress = progress
	goal.flags.ignore_mandatory = True
	goal.save()

	return goal


@frappe.whitelist()
def update_status(status: str, goals: str | list) -> None:
	if isinstance(goals, str):
		import json

		goals = json.loads(goals)

	for goal in goals:
		goal = frappe.get_doc("Goal", goal)
		goal.status = status
		if status == "Completed":
			goal.progress = 100
		goal.flags.ignore_mandatory = True
		goal.save()

	return goals


@frappe.whitelist()
def add_tree_node():
	from frappe.desk.treeview import make_tree_args

	args = frappe.form_dict
	args = make_tree_args(**args)

	if args.parent_goal == "All Goals" or not frappe.db.exists("Goal", args.parent_goal):
		args.parent_goal = None

	frappe.get_doc(args).insert()
