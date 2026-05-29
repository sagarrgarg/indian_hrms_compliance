# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import getdate
from frappe.utils.nestedset import NestedSet

SCOPE_FIELDS = (
	"assigned_to_department",
	"assigned_to_designation",
	"assigned_to_branch",
	"assigned_to_grade",
	"assigned_to_employment_type",
	"assigned_to_employee_group",
)


class HRMSTask(NestedSet):
	nsm_parent_field = "parent_task"

	def validate(self):
		self._validate_weight()
		self._validate_dates()
		self._validate_scope()
		self._validate_approval_routing()
		self._validate_kpi_fields()

	def _validate_weight(self):
		if self.weight is not None and (self.weight < 0 or self.weight > 100):
			frappe.throw(_("Weight must be between 0 and 100."))

	def _validate_dates(self):
		if self.effective_from and self.effective_to:
			if getdate(self.effective_to) < getdate(self.effective_from):
				frappe.throw(_("'Effective To' cannot be earlier than 'Effective From'."))
		if self.status == "Active" and not self.effective_from:
			frappe.throw(_("'Effective From' is required when status is Active."))

	def _validate_scope(self):
		"""At least one scope rule must be set, unless 'Applicable to All Active' is ticked.
		SOP Containers (is_group) inherit assignment from their child tasks."""
		if self.applicable_to_all_active:
			return
		if self.is_group:
			return
		if not any(self.get(f) for f in SCOPE_FIELDS):
			frappe.throw(
				_(
					"Specify at least one assignment scope (Department / Designation / "
					"Branch / Grade / Employment Type / Employee Group), or tick "
					"'Applicable to All Active Employees'."
				)
			)

	def _validate_approval_routing(self):
		if not self.requires_approval:
			return
		if self.approver_resolution == "Specific User" and not self.approver_user:
			frappe.throw(_("Approver User is required when approver resolution is 'Specific User'."))
		if self.approver_resolution == "Specific Role" and not self.approver_role:
			frappe.throw(_("Approver Role is required when approver resolution is 'Specific Role'."))

	def _validate_kpi_fields(self):
		if self.completion_type != "Numeric Entry":
			return
		if self.target_value is None:
			frappe.msgprint(
				_("Target Value is empty for this KPI Metric — KPI achievement % won't compute until set."),
				indicator="orange",
				alert=True,
			)
