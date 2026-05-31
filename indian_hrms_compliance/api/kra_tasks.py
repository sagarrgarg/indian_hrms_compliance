# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""HR-only CRUD for KRAs and HRMS Tasks, surfaced in the PWA cockpit.

Every endpoint is guarded for HR roles and company-scoped to the HR user's own
Company (resolved from their Employee record). Administrator / a user with no
Employee record operates across all companies and must pass `company`
explicitly on create.
"""

import frappe
from frappe import _

from indian_hrms_compliance.api.cockpit import COCKPIT_ROLES, _scope_company

KRA_FIELDS = (
	"title", "kra_category", "color", "status", "owner_designation",
	"company", "description", "detailed_description", "success_criteria",
)
TASK_FIELDS = (
	"task_name", "kra", "task_kind", "color", "status", "effective_from",
	"effective_to", "company", "frequency", "expected_count_per_period",
	"weight", "completion_type", "requires_attachment", "attachment_label",
	"requires_approval", "approver_resolution", "approver_user", "approver_role",
	"applicable_to_all_active", "assigned_to_department", "assigned_to_designation",
	"assigned_to_branch", "assigned_to_grade", "assigned_to_employment_type",
	"assigned_to_employee_group", "description",
)


def _guard():
	frappe.only_for(COCKPIT_ROLES)


def _company_filter():
	company = _scope_company()
	return ({"company": company} if company else {}), company


def _assert_in_scope(company):
	"""A scoped HR user can only touch records in their own Company."""
	scope = _scope_company()
	if scope and company != scope:
		frappe.throw(_("You can only manage records for {0}.").format(scope))


# ------------------------------------------------------------------------ KRA
@frappe.whitelist()
def list_kras():
	_guard()
	filters, _company = _company_filter()
	rows = frappe.get_all(
		"KRA",
		filters=filters,
		fields=[
			"name", "title", "kra_category", "status", "color", "owner_designation",
			"company", "description", "open_task_instance_count",
		],
		order_by="status asc, title asc",
	)
	# task_count on KRA is only refreshed on KRA save — compute it live so the
	# list reflects tasks added/removed since.
	live_counts = {}
	for r in frappe.get_all(
		"HRMS Task",
		filters={"status": "Active", "kra": ("in", [r.name for r in rows] or ["__none__"])},
		fields=["kra", "count(name) as n"],
		group_by="kra",
	):
		live_counts[r.kra] = r.n
	for r in rows:
		r["task_count"] = live_counts.get(r.name, 0)
	return rows


@frappe.whitelist()
def get_kra(name):
	_guard()
	doc = frappe.get_doc("KRA", name)
	_assert_in_scope(doc.company)
	return doc.as_dict()


@frappe.whitelist()
def save_kra(values):
	_guard()
	d = frappe.parse_json(values) if isinstance(values, str) else dict(values or {})
	scope = _scope_company()
	if scope:
		d["company"] = scope
	if not d.get("company"):
		frappe.throw(_("Company is required."))
	_assert_in_scope(d["company"])

	if d.get("name"):
		doc = frappe.get_doc("KRA", d["name"])
		_assert_in_scope(doc.company)
	else:
		doc = frappe.new_doc("KRA")
	for f in KRA_FIELDS:
		if f in d:
			doc.set(f, d[f])
	doc.save()
	return {"name": doc.name, "title": doc.title}


@frappe.whitelist()
def delete_kra(name):
	_guard()
	doc = frappe.get_doc("KRA", name)
	_assert_in_scope(doc.company)
	linked = frappe.db.count("HRMS Task", {"kra": name})
	if linked:
		frappe.throw(
			_("Cannot delete — {0} HRMS Task(s) still roll up to this KRA. Archive it instead.").format(linked)
		)
	frappe.delete_doc("KRA", name)
	return {"deleted": name}


# ------------------------------------------------------------------- HRMS Task
@frappe.whitelist()
def list_hrms_tasks():
	_guard()
	filters, _company = _company_filter()
	filters["is_group"] = 0
	rows = frappe.get_all(
		"HRMS Task",
		filters=filters,
		fields=[
			"name", "task_name", "kra", "task_kind", "status", "frequency",
			"company", "applicable_to_all_active", "effective_from", "effective_to",
		],
		order_by="status asc, task_name asc",
	)
	return rows


@frappe.whitelist()
def get_hrms_task(name):
	_guard()
	doc = frappe.get_doc("HRMS Task", name)
	_assert_in_scope(doc.company)
	return doc.as_dict()


@frappe.whitelist()
def save_hrms_task(values):
	_guard()
	d = frappe.parse_json(values) if isinstance(values, str) else dict(values or {})
	scope = _scope_company()
	if scope:
		d["company"] = scope
	if not d.get("company"):
		frappe.throw(_("Company is required."))
	_assert_in_scope(d["company"])

	if d.get("name"):
		doc = frappe.get_doc("HRMS Task", d["name"])
		_assert_in_scope(doc.company)
	else:
		doc = frappe.new_doc("HRMS Task")
	for f in TASK_FIELDS:
		if f in d:
			doc.set(f, d[f])
	doc.save()
	return {"name": doc.name, "task_name": doc.task_name}


@frappe.whitelist()
def delete_hrms_task(name):
	_guard()
	doc = frappe.get_doc("HRMS Task", name)
	_assert_in_scope(doc.company)
	instances = frappe.db.count("Goal", {"task_template": name})
	if instances:
		frappe.throw(
			_("Cannot delete — {0} Task Instance(s) exist for this task. Retire it instead.").format(instances)
		)
	frappe.delete_doc("HRMS Task", name)
	return {"deleted": name}


# ------------------------------------------------------------------- options
@frappe.whitelist()
def get_form_options():
	"""Link-field choices the manage view needs, all company-scoped."""
	_guard()
	filters, company = _company_filter()
	kras = frappe.get_all(
		"KRA", filters={**filters, "status": "Active"}, fields=["name", "title"], order_by="title asc"
	)
	designations = frappe.get_all("Designation", fields=["name"], order_by="name asc")
	departments = frappe.get_all("Department", filters=dict(filters), fields=["name"], order_by="name asc")
	return {
		"company": company,
		"kras": kras,
		"designations": [r.name for r in designations],
		"departments": [r.name for r in departments],
		"frequencies": ["One-time", "Daily", "Weekly", "Monthly", "Quarterly", "Yearly", "On-demand"],
		"completion_types": ["Checkbox", "Document Upload", "Numeric Entry", "Form", "Approval Only"],
		"kra_categories": [
			"Operational", "Strategic", "Compliance", "Quality", "Financial",
			"Customer", "People", "Safety", "Other",
		],
	}
