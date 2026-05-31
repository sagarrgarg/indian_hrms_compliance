# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""New Employee Setup — one guided form that creates the whole employee.

On "Create Employee" it runs the onboarding SOP in one go:
  1. Employee (Active) with statutory IDs, reporting manager and approvers.
  2. An enabled User login + Company-scoped User Permission (native
     create_user_permission flag adds Company + Employee permissions).
  3. Salary Structure Assignment (submitted).
  4. Leave Policy auto-assignment fires via the Employee activation hook when
     the company's leave defaults are configured.

Employee + User creation is atomic (rolls back together on failure). Salary /
shift are best-effort: a failure there is logged and noted but does not undo
the employee.
"""

import frappe
from frappe import _
from frappe.model.document import Document

ESS_ROLES = ("Employee", "Employee Self Service")


class NewEmployeeSetup(Document):
	def validate(self):
		if self.create_user and not self.user_email:
			frappe.throw(_("User Email is required to create a User login."))

	@frappe.whitelist()
	def create_employee_and_setup(self):
		frappe.only_for(("HR Manager", "HR User", "System Manager"))
		if self.created_employee:
			frappe.throw(
				_("An Employee was already created from this form: {0}").format(self.created_employee)
			)

		log = []

		# --- Critical path: Employee + User (atomic) ---
		sp_core = "nes_core"
		frappe.db.savepoint(sp_core)
		try:
			emp = self._create_employee()
			log.append(_("Employee {0} created (Active).").format(emp.name))

			if self.create_user:
				user_name = self._create_user(emp)
				perm = _(" + Company-scoped permission") if self.create_user_permission else ""
				log.append(_("User {0} created{1}.").format(user_name, perm))
				if getattr(self, "_welcome_email_failed", False):
					log.append(
						_(
							"⚠ Welcome email could not be sent (check the sender Email Account / "
							"site encryption key). Share login details manually."
						)
					)
		except Exception:
			try:
				frappe.db.rollback(save_point=sp_core)
			except Exception:
				pass
			frappe.log_error(title="New Employee Setup: core failed", message=frappe.get_traceback())
			raise

		# --- Best-effort: Salary Structure Assignment ---
		if self.salary_structure:
			sp_sal = "nes_salary"
			frappe.db.savepoint(sp_sal)
			try:
				ssa = self._assign_salary(emp)
				log.append(_("Salary Structure Assignment {0} submitted.").format(ssa))
			except Exception:
				try:
					frappe.db.rollback(save_point=sp_sal)
				except Exception:
					pass
				frappe.log_error(title="New Employee Setup: salary failed", message=frappe.get_traceback())
				log.append(_("⚠ Salary Structure Assignment failed — assign it manually (see Error Log)."))

		# Leave Policy auto-assignment is fired by the Employee activation hook.
		lpa = frappe.db.exists("Leave Policy Assignment", {"employee": emp.name, "docstatus": 1})
		if lpa:
			log.append(_("Leave Policy auto-assigned ({0}).").format(lpa))
		else:
			log.append(_("Leave Policy not auto-assigned (set company defaults + toggle, or assign manually)."))

		self.created_employee = emp.name
		self.created_user = emp.user_id
		self.setup_log = "\n".join(log)
		self.save()
		return {"employee": emp.name, "user": emp.user_id, "log": log}

	def _create_employee(self):
		emp = frappe.new_doc("Employee")
		emp.update(
			{
				"first_name": self.first_name,
				"middle_name": self.middle_name,
				"last_name": self.last_name,
				"company": self.company,
				"department": self.department,
				"designation": self.designation,
				"grade": self.grade,
				"date_of_joining": self.date_of_joining,
				"date_of_birth": self.date_of_birth,
				"gender": self.gender,
				"employment_type": self.employment_type,
				"status": "Active",
				"pan_number": self.pan_number,
				"aadhaar_last_4": self.aadhaar_last_4,
				"uan_number": self.uan_number,
				"provident_fund_account": self.provident_fund_account,
				"esic_ip_number": self.esic_ip_number,
				"bank_name": self.bank_name,
				"bank_ac_no": self.bank_ac_no,
				"ifsc_code": self.ifsc_code,
				"reports_to": self.reports_to,
				"leave_approver": self.leave_approver,
				"expense_approver": self.expense_approver,
				"shift_request_approver": self.shift_request_approver,
				"default_shift": self.default_shift,
				"create_user_permission": 1 if (self.create_user and self.create_user_permission) else 0,
			}
		)
		if self.user_email:
			emp.personal_email = self.user_email
			emp.prefered_contact_email = "Personal Email"
		emp.insert()
		return emp

	def _create_user(self, emp):
		if frappe.db.exists("User", self.user_email):
			user = frappe.get_doc("User", self.user_email)
		else:
			user = frappe.new_doc("User")
			user.update(
				{
					"email": self.user_email,
					"first_name": self.first_name,
					"middle_name": self.middle_name,
					"last_name": self.last_name,
					"enabled": 1,
					"user_type": "System User",
					# Never send the welcome email during insert. It sends synchronously
					# and a broken/OAuth email account (e.g. wrong encryption key on a
					# restored site) would abort employee creation. Sent best-effort below.
					"send_welcome_email": 0,
					"gender": self.gender,
					"birth_date": self.date_of_birth,
				}
			)
			user.insert()

		# Link the employee FIRST: validate_employee_role strips Employee/ESS roles
		# from any User that isn't mapped to an Employee. Linking also triggers the
		# native update_user_permissions (adds Company + Employee User Permissions).
		emp.user_id = user.name
		emp.save()

		roles = [r for r in ESS_ROLES if frappe.db.exists("Role", r)]
		if roles:
			user.reload()
			user.add_roles(*roles)

		# Best-effort welcome email — must never roll back the new employee.
		if self.send_welcome_email:
			try:
				user.reload()
				user.send_welcome_mail_to_user()
			except Exception:
				self._welcome_email_failed = True
				frappe.log_error(
					title="New Employee Setup: welcome email failed",
					message=frappe.get_traceback(),
				)
		return user.name

	def _assign_salary(self, emp):
		from_date = self.payroll_effective_date or self.date_of_joining
		ssa = frappe.new_doc("Salary Structure Assignment")
		ssa.employee = emp.name
		ssa.salary_structure = self.salary_structure
		ssa.company = self.company
		ssa.from_date = from_date
		if self.base:
			ssa.base = self.base
		# Tax is statutory, not a per-hire choice: auto-attach the applicable
		# Income Tax Slab so a TDS-bearing structure assigns without manual input.
		ssa.income_tax_slab = _default_income_tax_slab(self.company, from_date)
		ssa.insert()
		ssa.submit()
		return ssa.name


def _default_income_tax_slab(company, on_date):
	"""Resolve the Income Tax Slab to apply: the latest active, submitted slab
	effective on/before the date, preferring a company-specific one over a
	general (company-less) slab."""
	slabs = frappe.get_all(
		"Income Tax Slab",
		filters={
			"docstatus": 1,
			"disabled": 0,
			"effective_from": ("<=", on_date),
		},
		or_filters=[{"company": company}, {"company": ["in", ("", None)]}],
		fields=["name", "company", "effective_from"],
		order_by="effective_from desc",
	)
	if not slabs:
		return None
	# Prefer a slab tied to this company; else fall back to a general one.
	for s in slabs:
		if s.company == company:
			return s.name
	return slabs[0].name
