# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class EmployeePolicyAcknowledgement(Document):
	def validate(self):
		before = self.get_doc_before_save()
		# Once acknowledged, the record is immutable on status (audit integrity).
		if before and before.status == "Acknowledged" and self.status != "Acknowledged":
			frappe.throw(_("Cannot revert an acknowledged policy. Create a new policy version instead."))

	def acknowledge(self, via="Desk"):
		"""Mark this acknowledgement as Acknowledged. Idempotent."""
		if self.status == "Acknowledged":
			return
		self.status = "Acknowledged"
		self.acknowledged_at = now()
		self.acknowledged_via = via
		ip = _client_ip()
		if ip:
			self.ip_address = ip
		self.save(ignore_permissions=True)


def _client_ip():
	if not getattr(frappe.local, "request", None):
		return None
	xff = frappe.local.request.headers.get("X-Forwarded-For")
	if xff:
		return xff.split(",")[0].strip()
	return frappe.local.request.remote_addr


@frappe.whitelist()
def acknowledge_policy(name, via="Desk"):
	"""Whitelisted: the current user acknowledges one of their assigned policies.

	Authorization: either (a) the current session user is the Employee linked
	to this acknowledgement, or (b) the current session user holds an HR
	role (HR Manager / HR User / System Manager) and is acting on behalf.
	Plain Employee role on the doctype is NOT enough — it grants generic
	doctype access, not the right to acknowledge somebody else's record.
	"""
	ack = frappe.get_doc("Employee Policy Acknowledgement", name)
	emp_user = frappe.db.get_value("Employee", ack.employee, "user_id")
	if frappe.session.user != emp_user:
		roles = set(frappe.get_roles())
		if not roles & {"HR Manager", "HR User", "System Manager"}:
			frappe.throw(
				_("You are not permitted to acknowledge this policy."),
				frappe.PermissionError,
			)
	# Auto-detect PWA vs Desk from referer.
	if via == "Desk" and getattr(frappe.local, "request", None):
		referrer = frappe.local.request.referrer or ""
		if "/indian_hrms_compliance" in referrer or "/frontend" in referrer:
			via = "PWA"
	ack.acknowledge(via=via)
	return {"name": ack.name, "status": ack.status, "acknowledged_at": str(ack.acknowledged_at)}


@frappe.whitelist()
def get_my_pending_acknowledgements():
	"""Return Pending acknowledgements for the current user's Active Employee(s)."""
	employees = frappe.get_all(
		"Employee",
		filters={"user_id": frappe.session.user, "status": "Active"},
		pluck="name",
	)
	if not employees:
		return []
	return frappe.get_all(
		"Employee Policy Acknowledgement",
		filters={"employee": ("in", employees), "status": "Pending"},
		fields=[
			"name",
			"employee",
			"company",
			"policy",
			"policy_name_fetched",
			"policy_version",
			"policy_category",
			"due_date",
			"signed_text",
		],
		order_by="due_date asc",
	)


def get_permission_query_conditions(user):
	"""Employees see only their own acknowledgements; HR roles see everything."""
	if not user:
		user = frappe.session.user
	roles = frappe.get_roles(user)
	if "HR Manager" in roles or "HR User" in roles or "System Manager" in roles:
		return ""
	employees = frappe.get_all(
		"Employee", filters={"user_id": user}, pluck="name"
	)
	if not employees:
		return "1=0"
	emp_list = "', '".join(employees)
	return f"`tabEmployee Policy Acknowledgement`.employee in ('{emp_list}')"
