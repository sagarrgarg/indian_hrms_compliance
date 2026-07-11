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
from frappe.utils import add_months, cint, flt, getdate

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
	if cint(d.create_user) and not d.user_email:
		frappe.throw(_("User Email is required to create a User login."))
	if not d.leave_policy:
		frappe.throw(_("Leave Policy is required."))
	if not d.default_shift:
		frappe.throw(_("Default Shift is required."))

	log = []
	state = {"welcome_email_failed": False}

	# --- Critical path: Employee + User (atomic) ---
	# Suppress the company-default leave + blanket policy activation hooks for the
	# whole Employee insert/save: the page assigns the Leave Policy and enrols the
	# curated policy set explicitly below, so the hooks must not also fire.
	frappe.flags.in_new_employee_setup = True
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
	finally:
		frappe.flags.in_new_employee_setup = False

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

	# --- Best-effort: Shift Assignment (shift is assignment-based, not a field) ---
	if d.default_shift:
		sp_shift = "nes_shift"
		frappe.db.savepoint(sp_shift)
		try:
			sa_name = _assign_shift(d, emp)
			log.append(_("Shift Assignment {0} submitted.").format(sa_name))
		except Exception:
			try:
				frappe.db.rollback(save_point=sp_shift)
			except Exception:
				pass
			frappe.log_error(title="Employee Setup: shift failed", message=frappe.get_traceback())
			log.append(_("⚠ Shift Assignment failed — assign the shift manually (see Error Log)."))

	# --- Best-effort: Leave Policy Assignment (exactly what HR picked) ---
	if d.leave_policy:
		sp_leave = "nes_leave"
		frappe.db.savepoint(sp_leave)
		try:
			lpa_name = _assign_leave_policy(d, emp)
			log.append(_("Leave Policy Assignment {0} submitted.").format(lpa_name))
		except Exception:
			try:
				frappe.db.rollback(save_point=sp_leave)
			except Exception:
				pass
			frappe.log_error(title="Employee Setup: leave policy failed", message=frappe.get_traceback())
			log.append(_("⚠ Leave Policy Assignment failed — assign it manually (see Error Log)."))

	# --- Best-effort: enrol the curated company policies for acknowledgement ---
	policies = d.policies_to_ack
	if isinstance(policies, str):
		policies = json.loads(policies or "[]")
	if policies:
		sp_ack = "nes_acks"
		frappe.db.savepoint(sp_ack)
		try:
			from indian_hrms_compliance.hr.doctype.hrms_policy.hrms_policy import (
				create_acknowledgements_for_employee,
			)

			n = create_acknowledgements_for_employee(emp.name, only_policies=policies)
			log.append(
				_("Queued {0} policy acknowledgement(s).").format(n)
				if n
				else _("No new policy acknowledgements were needed.")
			)
		except Exception:
			try:
				frappe.db.rollback(save_point=sp_ack)
			except Exception:
				pass
			frappe.log_error(title="Employee Setup: policy acks failed", message=frappe.get_traceback())
			log.append(_("⚠ Policy acknowledgements failed — see Error Log."))

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
			"aadhaar_number": d.aadhaar_number,
			"aadhaar_last_4": d.aadhaar_last_4 or ((d.aadhaar_number or "")[-4:] or None),
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
			# Shift is assignment-based, not a field: a submitted Shift Assignment is
			# created below (best-effort) so attendance/holidays resolve from the Shift
			# Type. Writing Employee.default_shift here would duplicate that source.
			# Setting job_applicant here lets the Employee after_insert cascade mark
			# the linked Job Applicant (and any Job Offer) as Accepted.
			"job_applicant": d.job_applicant or None,
			"create_user_permission": 1 if (cint(d.create_user) and cint(d.create_user_permission)) else 0,
		}
	)
	_apply_confirmation(emp, d)
	if d.user_email:
		emp.personal_email = d.user_email
		emp.prefered_contact_email = "Personal Email"
	emp.insert()
	return emp


def _apply_confirmation(emp, d):
	"""Set the employee's probation / confirmation state from the setup page.

	On probation: status field stays Active (so payroll/attendance/leave keep
	working) while confirmation_status=Probation flags it, and the expected
	confirmation date is DOJ + the chosen months (held in
	scheduled_confirmation_date, the same field the app's probation schedule
	hook uses). Otherwise, if HR supplied a Confirmation Date, mark Confirmed.
	"""
	if cint(d.place_on_probation):
		emp.confirmation_status = "Probation"
		months = cint(d.probation_months)
		if months > 0 and d.date_of_joining:
			emp.scheduled_confirmation_date = add_months(getdate(d.date_of_joining), months)
	elif d.final_confirmation_date:
		emp.confirmation_status = "Confirmed"
		emp.final_confirmation_date = getdate(d.final_confirmation_date)


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


def _assign_shift(d, emp):
	"""Create + submit a Shift Assignment from the joining date (open-ended).

	The shift is the single source for attendance processing and holidays (via
	Shift Type.holiday_list), replacing the old Employee.default_shift field.
	"""
	sa = frappe.new_doc("Shift Assignment")
	sa.employee = emp.name
	sa.shift_type = d.default_shift
	sa.company = d.company
	sa.start_date = d.date_of_joining
	sa.status = "Active"
	sa.insert()
	sa.submit()
	return sa.name


def _assign_leave_policy(d, emp):
	"""Create + submit a Leave Policy Assignment for the policy HR picked.

	Leave Period based when a period is chosen (the controller derives the
	effective dates from it); otherwise Joining Date based (dates derived from
	the employee's DOJ). Submitting cascades into Leave Allocations.
	"""
	from indian_hrms_compliance.hr.doctype.leave_policy_assignment.leave_policy_assignment import (
		create_assignment,
	)

	data = frappe._dict(leave_policy=d.leave_policy, carry_forward=0)
	if d.leave_period:
		data.assignment_based_on = "Leave Period"
		data.leave_period = d.leave_period
	else:
		data.assignment_based_on = "Joining Date"
	assignment = create_assignment(emp.name, data)
	assignment.submit()
	return assignment.name


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


@frappe.whitelist()
def get_setup_defaults(company: str | None = None) -> dict:
	"""Per-company defaults the New Employee Setup page prefills: the company's
	default Leave Policy + Leave Period, a suggested probation length (from HR
	Settings), and the company's Active acknowledgement-requiring policies to
	offer (pre-checked) for the new joiner."""
	frappe.only_for(SETUP_ROLES)
	out = {"leave_policy": None, "leave_period": None, "probation_months": None, "policies": []}
	if not company:
		return out

	from indian_hrms_compliance.hr.leave_period_setup import get_current_leave_period

	out["leave_policy"] = frappe.get_cached_value("Company", company, "default_leave_policy")
	# Leave period is derived from the Fiscal Year (India), not a company field.
	out["leave_period"] = get_current_leave_period()

	days = cint(frappe.db.get_single_value("HR Settings", "default_probation_period_days"))
	if days > 0:
		out["probation_months"] = max(1, round(days / 30))

	out["policies"] = frappe.get_all(
		"HRMS Policy",
		filters={"status": "Active", "requires_acknowledgement": 1, "company": company},
		fields=["name", "policy_name", "version"],
		order_by="policy_name asc",
	)
	return out
