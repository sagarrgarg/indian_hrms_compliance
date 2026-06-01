# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""New Employee Setup — guided onboarding orchestration (page-driven).

setup_new_employee(data) creates, in one go:
  1. Employee (Active) with statutory IDs, reporting manager and approvers.
  2. An enabled User login + Company-scoped User Permission (native
     create_user_permission flag adds Company + Employee permissions).
  3. Salary Structure Assignment (submitted) with the applicable Income Tax Slab.
  4. Leave Policy auto-assignment fires via the Employee activation hook.

Employee + User creation is atomic; salary is best-effort (logged, not fatal).
Backed by the "New Employee Setup" Desk page (no per-run doctype record).
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt

ESS_ROLES = ("Employee", "Employee Self Service")
SETUP_ROLES = ("HR Manager", "HR User", "System Manager")


@frappe.whitelist()
def setup_new_employee(data):
	frappe.only_for(SETUP_ROLES)
	if isinstance(data, str):
		data = json.loads(data)
	d = frappe._dict(data or {})

	if not d.first_name:
		frappe.throw(_("First Name is required."))
	if not d.company:
		frappe.throw(_("Company is required."))
	if not d.gender:
		frappe.throw(_("Gender is required."))
	if not d.date_of_birth:
		frappe.throw(_("Date of Birth is required."))
	if not d.date_of_joining:
		frappe.throw(_("Date of Joining is required."))
	if not d.pan_number:
		frappe.throw(_("PAN is required."))
	if cint(d.create_user) and not d.user_email:
		frappe.throw(_("User Email is required to create a User login."))

	log = []
	state = {"welcome_email_failed": False}

	# --- Critical path: Employee + User (atomic) ---
	sp_core = "nes_core"
	frappe.db.savepoint(sp_core)
	try:
		emp = _create_employee(d)
		log.append(_("Employee {0} created (Active).").format(emp.name))
		if cint(d.create_user):
			user_name = _create_user(d, emp, state)
			perm = _(" + Company-scoped permission") if cint(d.create_user_permission) else ""
			log.append(_("User {0} created{1}.").format(user_name, perm))
			if state["welcome_email_failed"]:
				log.append(
					_("⚠ Welcome email could not be sent (check the sender Email Account / site encryption key).")
				)
	except Exception:
		try:
			frappe.db.rollback(save_point=sp_core)
		except Exception:
			pass
		frappe.log_error(title="Employee Setup: core failed", message=frappe.get_traceback())
		raise

	# --- Best-effort: Salary Structure Assignment ---
	if d.salary_structure:
		sp_sal = "nes_salary"
		frappe.db.savepoint(sp_sal)
		try:
			ssa = _assign_salary(d, emp)
			log.append(_("Salary Structure Assignment {0} submitted.").format(ssa))
		except Exception:
			try:
				frappe.db.rollback(save_point=sp_sal)
			except Exception:
				pass
			frappe.log_error(title="Employee Setup: salary failed", message=frappe.get_traceback())
			log.append(_("⚠ Salary Structure Assignment failed — assign it manually (see Error Log)."))

	lpa = frappe.db.exists("Leave Policy Assignment", {"employee": emp.name, "docstatus": 1})
	log.append(
		_("Leave Policy auto-assigned ({0}).").format(lpa)
		if lpa
		else _("Leave Policy not auto-assigned (set company defaults + toggle, or assign manually).")
	)

	# Launched from a self-service onboarding application? Close the loop.
	if d.onboarding_application:
		from indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application import (
			mark_converted,
		)

		mark_converted(d.onboarding_application, emp.name)
		log.append(_("Onboarding application {0} marked Converted.").format(d.onboarding_application))

	frappe.db.commit()
	return {"employee": emp.name, "user": emp.user_id, "log": log}


def _create_employee(d):
	emp = frappe.new_doc("Employee")
	emp.update(
		{
			"first_name": d.first_name,
			"middle_name": d.middle_name,
			"last_name": d.last_name,
			"company": d.company,
			"department": d.department,
			"designation": d.designation,
			"grade": d.grade,
			"date_of_joining": d.date_of_joining,
			"date_of_birth": d.date_of_birth,
			"gender": d.gender,
			"employment_type": d.employment_type,
			"status": "Active",
			"pan_number": d.pan_number,
			"aadhaar_last_4": d.aadhaar_last_4,
			"uan_number": d.uan_number,
			"provident_fund_account": d.provident_fund_account,
			"esic_ip_number": d.esic_ip_number,
			"bank_name": d.bank_name,
			"bank_ac_no": d.bank_ac_no,
			"ifsc_code": d.ifsc_code,
			"reports_to": d.reports_to,
			"leave_approver": d.leave_approver,
			"expense_approver": d.expense_approver,
			"shift_request_approver": d.shift_request_approver,
			"default_shift": d.default_shift,
			"create_user_permission": 1 if (cint(d.create_user) and cint(d.create_user_permission)) else 0,
		}
	)
	if d.user_email:
		emp.personal_email = d.user_email
		emp.prefered_contact_email = "Personal Email"
	emp.insert()
	return emp


def _create_user(d, emp, state):
	if frappe.db.exists("User", d.user_email):
		user = frappe.get_doc("User", d.user_email)
	else:
		user = frappe.new_doc("User")
		user.update(
			{
				"email": d.user_email,
				"first_name": d.first_name,
				"middle_name": d.middle_name,
				"last_name": d.last_name,
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,  # sent best-effort after linking
				"gender": d.gender,
				"birth_date": d.date_of_birth,
			}
		)
		user.insert()

	# Link the employee FIRST: validate_employee_role strips Employee/ESS roles
	# from any User not mapped to an Employee. Linking also adds the native
	# Company + Employee User Permissions (create_user_permission).
	emp.user_id = user.name
	emp.save()

	roles = [r for r in ESS_ROLES if frappe.db.exists("Role", r)]
	if roles:
		user.reload()
		user.add_roles(*roles)

	if cint(d.send_welcome_email):
		try:
			user.reload()
			user.send_welcome_mail_to_user()
		except Exception:
			state["welcome_email_failed"] = True
			frappe.log_error(title="Employee Setup: welcome email failed", message=frappe.get_traceback())
	return user.name


def _assign_salary(d, emp):
	from_date = d.payroll_effective_date or d.date_of_joining
	ssa = frappe.new_doc("Salary Structure Assignment")
	ssa.employee = emp.name
	ssa.salary_structure = d.salary_structure
	ssa.company = d.company
	ssa.from_date = from_date
	if d.base:
		ssa.base = flt(d.base)
	ssa.income_tax_slab = d.income_tax_slab or _default_income_tax_slab(d.company, from_date)
	ssa.insert()
	ssa.submit()
	return ssa.name


def _default_income_tax_slab(company, on_date):
	slabs = frappe.get_all(
		"Income Tax Slab",
		filters={"docstatus": 1, "disabled": 0, "effective_from": ("<=", on_date)},
		or_filters=[{"company": company}, {"company": ("in", ("", None))}],
		fields=["name", "company", "effective_from"],
		order_by="effective_from desc",
	)
	if not slabs:
		return None
	for s in slabs:
		if s.company == company:
			return s.name
	return slabs[0].name
