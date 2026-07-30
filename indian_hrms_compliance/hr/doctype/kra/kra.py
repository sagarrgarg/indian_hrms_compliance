# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


def effective_dri(kra_row) -> str | None:
	"""Who is accountable for this KRA RIGHT NOW.

	The Acting DRI, while set and within its cover window, stands in for the
	DRI (leave / interim vacancy). Otherwise the DRI. `kra_row` may be a
	Document or any dict-like row carrying dri / acting_dri / acting_until.
	Shared so the KRA form and the nightly integrity check agree on one answer.
	"""
	get = kra_row.get if hasattr(kra_row, "get") else lambda k: getattr(kra_row, k, None)
	acting = get("acting_dri")
	until = get("acting_until")
	if acting and (not until or getdate(until) >= getdate(today())):
		return acting
	return get("dri")


class KRA(Document):
	def validate(self):
		self._validate_dri()
		self._validate_acting_cover()
		self._refresh_usage_counts()

	def _validate_acting_cover(self):
		"""Acting cover must be a real, current employee of this company, and an
		'until' date without an acting person is meaningless."""
		if self.acting_until and not self.acting_dri:
			self.acting_until = None
		if not self.acting_dri:
			return
		emp = frappe.db.get_value(
			"Employee", self.acting_dri, ["status", "company"], as_dict=True
		)
		if not emp or emp.status != "Active":
			frappe.throw(_("The Acting DRI must be an active employee."), title=_("Invalid Acting DRI"))
		if self.company and emp.company and emp.company != self.company:
			frappe.throw(
				_("The Acting DRI must belong to the same company as this KRA."),
				title=_("Company Mismatch"),
			)
		if self.acting_until and getdate(self.acting_until) < getdate(today()):
			frappe.msgprint(
				_("Acting cover has already expired ({0}) — this KRA has reverted to its DRI.").format(
					self.acting_until
				),
				indicator="orange",
				alert=True,
			)

	def _validate_dri(self):
		"""An Active KRA must name exactly one accountable person — its DRI.

		"Who's the DRI on that?" only works if the answer is a person, not a
		committee and not a vacancy. `owner_designation` says which ROLE owns
		the area; `dri` says who holds it today.

		Hard-enforced on new records so incoming data is always clean; existing
		records only warn, so adopting this never blocks edits to KRAs that
		predate the field.
		"""
		if self.status != "Active" or self.dri:
			return
		msg = _("An Active KRA needs a DRI — the single person accountable for it.")
		if self.is_new():
			frappe.throw(msg, title=_("DRI Required"))
		frappe.msgprint(msg, indicator="orange", alert=True)

	def on_update(self):
		self._warn_if_dri_inactive()

	def _warn_if_dri_inactive(self):
		"""Surface a DRI who has left, rather than silently keeping a dead owner.

		Honours acting cover: a valid Acting DRI means the KRA is NOT orphaned, so
		no warning. Step 1 reports on save; the nightly Org Integrity Check
		escalates to the reporting manager.
		"""
		if self.status != "Active":
			return
		holder = effective_dri(self)
		if not holder:
			return
		if frappe.db.get_value("Employee", holder, "status") != "Active":
			frappe.msgprint(
				_("The accountable owner for this KRA is no longer an active employee — reassign it.")
				+ f" ({holder})",
				indicator="red",
				alert=True,
			)

	def _refresh_usage_counts(self):
		"""Compute the three Usage (Auto) counters from current data.
		Three indexed COUNTs — cheap on save."""
		self.task_count = frappe.db.count(
			"HRMS Task", {"kra": self.name, "status": "Active"}
		)
		self.active_smart_goal_count = frappe.db.count(
			"Goal",
			{
				"kra": self.name,
				"goal_type": "SMART",
				"status": ("in", ["Pending", "In Progress"]),
			},
		)
		self.open_task_instance_count = frappe.db.count(
			"Goal",
			{
				"kra": self.name,
				"goal_type": "Task Instance",
				"status": ("in", ["Pending", "In Progress"]),
			},
		)
