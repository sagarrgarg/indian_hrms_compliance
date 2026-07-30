# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Playbook — the SOP-lite layer (L2).

The documented "how" for recurring work: a 3-bullet checklist for a startup, a
full versioned procedure for a regulated firm — the SAME doctype, dialled by how
much you fill in. An HRMS Task can point at one so the doer sees the steps as a
tick-through list. Replaces the old, dead "SOP Container" idea.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class Playbook(Document):
	def validate(self):
		self._validate_owner()
		self._bump_version()

	def _validate_owner(self):
		"""A named DRI, if set, must be a current employee of this company."""
		if not self.dri:
			return
		emp = frappe.db.get_value("Employee", self.dri, ["status", "company"], as_dict=True)
		if not emp or emp.status != "Active":
			frappe.throw(_("The Playbook owner (DRI) must be an active employee."))
		if self.company and emp.company and emp.company != self.company:
			frappe.throw(_("The Playbook owner must belong to the same company as the Playbook."))

	def _bump_version(self):
		"""Increment version whenever the STEPS change.

		A version identifies a step revision — the thing a task's evidence should
		be able to cite. New docs start at 1. Title is deliberately NOT a trigger:
		title is the document name (autoname field:title), so changing it is a
		rename, not a plain save, and versioning on it would be an unreliable
		promise. Housekeeping edits (kra, dri, status, reference) never bump.
		"""
		if self.is_new():
			if not self.version:
				self.version = 1
			return
		before = self.get_doc_before_save()
		if not before:
			return
		if self._steps_changed(before):
			self.version = (before.version or 1) + 1

	def _steps_changed(self, before) -> bool:
		def _snap(doc):
			return [
				(s.step_text or "", int(s.is_control_point or 0), s.expected_evidence or "")
				for s in (doc.steps or [])
			]

		return _snap(self) != _snap(before)


def _assert_playbook_visible(doc) -> None:
	"""A doer may read the playbook of their task; nobody may read a sibling
	company's SOPs. Enforce role permission AND company isolation server-side —
	the endpoint takes a raw, guessable name (autoname is the title), so the
	picker's company filter is not a security boundary on its own.
	"""
	frappe.has_permission("Playbook", "read", doc.name, throw=True)
	roles = set(frappe.get_roles())
	if {"HR Manager", "HR User", "System Manager"} & roles:
		return
	companies = frappe.get_all(
		"Employee",
		filters={"user_id": frappe.session.user, "status": "Active"},
		pluck="company",
	)
	if doc.company and companies and doc.company not in companies:
		frappe.throw(
			_("You do not have access to this playbook."), frappe.PermissionError
		)


@frappe.whitelist()
def get_playbook_steps(playbook: str) -> dict:
	"""The steps of a playbook, for the PWA task-detail tick-through checklist.

	Read-only reference: the checklist helps the doer follow the procedure; the
	task's own completion_type still captures the actual evidence. Returns an
	empty payload for a missing / retired playbook rather than erroring, so the
	task screen degrades gracefully. `name` is echoed back so the client can
	discard a stale response when the user has already navigated on.
	"""
	if not playbook or not frappe.db.exists("Playbook", playbook):
		return {"name": playbook, "title": None, "version": None, "steps": []}
	doc = frappe.get_cached_doc("Playbook", playbook)
	_assert_playbook_visible(doc)
	if doc.status == "Retired":
		return {"name": doc.name, "title": doc.title, "version": doc.version, "retired": 1, "steps": []}
	return {
		"name": doc.name,
		"title": doc.title,
		"version": doc.version,
		"reference_attachment": doc.reference_attachment,
		"steps": [
			{
				"step_text": s.step_text,
				"is_control_point": 1 if s.is_control_point else 0,
				"expected_evidence": s.expected_evidence,
			}
			for s in doc.steps
		],
	}
