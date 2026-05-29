# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class KRA(Document):
	def validate(self):
		self._validate_scope()
		self._refresh_usage_counts()

	def _validate_scope(self):
		"""If is_global is unticked, at least one applies_to_* hint must be set —
		otherwise the KRA would be orphaned (invisible everywhere when picker
		filters are enabled). Hints are advisory; existing links to this KRA
		are never invalidated."""
		if self.is_global:
			return
		if not (self.applies_to_department or self.applies_to_designation):
			frappe.throw(
				_(
					"This KRA is not Global. Pick at least one of "
					"'Applies to Department' or 'Applies to Designation' — "
					"otherwise the KRA will be invisible to picker filters."
				)
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
