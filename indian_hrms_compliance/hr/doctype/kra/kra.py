# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.model.document import Document


class KRA(Document):
	def validate(self):
		self._refresh_usage_counts()

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
