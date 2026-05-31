# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import re

import frappe
from frappe import _
from frappe.model.naming import set_name_by_naming_series
from frappe.utils import add_years, cint, get_link_to_form, getdate

from erpnext.setup.doctype.employee.employee import Employee

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
UAN_RE = re.compile(r"^[0-9]{12}$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
AADHAAR_LAST4_RE = re.compile(r"^[0-9]{4}$")


def _employee_link(name):
	# Relative URL — portable across host/port without depending on site_config host_name.
	return f'<a href="/app/employee/{name}">{name}</a>'

# Fields that must match across Employee records sharing the same user_id
# (they describe the human, not the employment).
PERSON_LEVEL_FIELDS = (
	"pan_number",
	"uan_number",
	"esic_ip_number",
	"aadhaar_last_4",
	"nps_pran",
	"date_of_birth",
	"gender",
)


def resolve_employee_approver(value):
	"""Resolve an Employee-typed approver field value to its linked ``user_id``.

	Employee.{leave,expense,shift_request}_approver now store an Employee, but the
	downstream approval engine (Leave Application / Expense Claim / Shift Request)
	and role/sharing/notification machinery all run on User. Use this at every
	boundary that feeds those.

	- Falsy values pass through unchanged.
	- An Employee resolves to its linked ``user_id``; an Employee with no linked
	  User resolves to ``None`` (never the Employee name, which would be an invalid
	  value for a User field).
	- A value that is already a User (e.g. a Department Approver row) passes through.
	"""
	if not value:
		return value
	if frappe.db.exists("Employee", value):
		return frappe.db.get_value("Employee", value, "user_id") or None
	return value


class EmployeeMaster(Employee):
	def autoname(self):
		naming_method = frappe.db.get_value("HR Settings", None, "emp_created_by")
		if not naming_method:
			frappe.throw(_("Please setup Employee Naming System in Human Resource > HR Settings"))
		else:
			if naming_method == "Naming Series":
				set_name_by_naming_series(self)
			elif naming_method == "Employee Number":
				self.name = self.employee_number
			elif naming_method == "Full Name":
				self.set_employee_name()
				self.name = self.employee_name

		self.employee = self.name

	def validate_duplicate_user_id(self):
		# Allow the same user_id across Companies. Hard-lock per (user_id, company)
		# when status == Active. Sequential rejoin (previous record Inactive/Left) is allowed.
		if not self.user_id:
			return
		duplicate = frappe.db.get_value(
			"Employee",
			{
				"user_id": self.user_id,
				"company": self.company,
				"status": "Active",
				"name": ("!=", self.name or ""),
			},
			"name",
		)
		if duplicate:
			frappe.throw(
				_("User {0} is already mapped to Active Employee {1} in {2}.").format(
					frappe.bold(self.user_id),
					_employee_link(duplicate),
					frappe.bold(self.company),
				),
				frappe.DuplicateEntryError,
			)


def validate_statutory_id_formats(doc, method=None):
	if doc.get("pan_number") and not PAN_RE.match(doc.pan_number):
		frappe.throw(_("PAN must match format AAAAA9999A (5 letters, 4 digits, 1 letter)."))
	if doc.get("uan_number") and not UAN_RE.match(doc.uan_number):
		frappe.throw(_("UAN must be exactly 12 digits."))
	if doc.get("ifsc_code") and not IFSC_RE.match(doc.ifsc_code):
		frappe.throw(_("IFSC must be 4 letters + '0' + 6 alphanumeric (e.g., HDFC0001234)."))
	if doc.get("aadhaar_last_4") and not AADHAAR_LAST4_RE.match(doc.aadhaar_last_4):
		frappe.throw(_("Aadhaar Last 4 Digits must be exactly 4 digits."))


def validate_person_data_consistency(doc, method=None):
	# When the same user_id appears on multiple Employee records, person-level
	# fields (PAN, UAN, ESIC IP, Aadhaar last-4, NPS PRAN, DOB, gender) must
	# agree across them. We only flag mismatches between *non-empty* values —
	# a blank on one Employee never contradicts a value on another.
	if not doc.user_id:
		return

	others = frappe.get_all(
		"Employee",
		filters={"user_id": doc.user_id, "name": ("!=", doc.name or "")},
		fields=["name", *PERSON_LEVEL_FIELDS],
	)
	if not others:
		return

	mismatches = []
	for other in others:
		for field in PERSON_LEVEL_FIELDS:
			mine = doc.get(field)
			theirs = other.get(field)
			if mine and theirs and str(mine) != str(theirs):
				mismatches.append((other.name, field, mine, theirs))

	if mismatches:
		lines = [
			_("{0} on Employee {1}: this record has {2}, other has {3}").format(
				frappe.bold(field), _employee_link(other_name), frappe.bold(str(mine)), frappe.bold(str(theirs))
			)
			for other_name, field, mine, theirs in mismatches
		]
		frappe.throw(
			_("Person-level fields must match across Employees linked to the same User:")
			+ "<br>"
			+ "<br>".join(lines),
			title=_("Statutory ID Mismatch"),
		)


def validate_single_primary_employer(doc, method=None):
	# Only one Active Employee per user_id may be the Primary Employer.
	if not (doc.user_id and doc.get("is_primary_employer")):
		return
	other = frappe.db.get_value(
		"Employee",
		{
			"user_id": doc.user_id,
			"is_primary_employer": 1,
			"status": "Active",
			"name": ("!=", doc.name or ""),
		},
		"name",
	)
	if other:
		frappe.throw(
			_("Employee {0} is already marked Primary Employer for {1}. Only one Primary Employer per User at a time.").format(
				_employee_link(other), frappe.bold(doc.user_id)
			),
			title=_("Duplicate Primary Employer"),
		)


def auto_set_probation_schedule(doc, method=None):
	"""On Employee validate, if confirmation_status is 'Probation' and the
	Scheduled Confirmation Date is empty, fill it from
	date_of_joining + HR Settings.default_probation_period_days.

	No-ops when scheduled_confirmation_date is already set (HR override),
	when confirmation_status isn't Probation, or when date_of_joining is missing.
	"""
	if doc.get("confirmation_status") != "Probation":
		return
	if doc.get("scheduled_confirmation_date"):
		return
	if not doc.get("date_of_joining"):
		return
	days = frappe.db.get_single_value("HR Settings", "default_probation_period_days")
	if not days or int(days) <= 0:
		return
	from frappe.utils import add_days

	doc.scheduled_confirmation_date = add_days(getdate(doc.date_of_joining), int(days))


def validate_onboarding_process(doc, method=None):
	"""Validates Employee Creation for linked Employee Onboarding"""
	if not doc.job_applicant:
		return

	employee_onboarding = frappe.get_all(
		"Employee Onboarding",
		filters={
			"job_applicant": doc.job_applicant,
			"docstatus": 1,
			"boarding_status": ("!=", "Completed"),
		},
	)
	if employee_onboarding:
		onboarding = frappe.get_doc("Employee Onboarding", employee_onboarding[0].name)
		onboarding.validate_employee_creation()
		onboarding.db_set("employee", doc.name)


def publish_update(doc, method=None):
	import indian_hrms_compliance

	indian_hrms_compliance.refetch_resource("indian_hrms_compliance:employee", doc.user_id)


def update_job_applicant_and_offer(doc, method=None):
	"""Updates Job Applicant and Job Offer status as 'Accepted' and submits them"""
	if not doc.job_applicant:
		return

	applicant_status_before_change = frappe.db.get_value("Job Applicant", doc.job_applicant, "status")
	if applicant_status_before_change != "Accepted":
		frappe.db.set_value("Job Applicant", doc.job_applicant, "status", "Accepted")
		frappe.msgprint(
			_("Updated the status of linked Job Applicant {0} to {1}").format(
				get_link_to_form("Job Applicant", doc.job_applicant), frappe.bold(_("Accepted"))
			)
		)
	offer_status_before_change = frappe.db.get_value(
		"Job Offer", {"job_applicant": doc.job_applicant, "docstatus": ["!=", 2]}, "status"
	)
	if offer_status_before_change and offer_status_before_change != "Accepted":
		job_offer = frappe.get_last_doc("Job Offer", filters={"job_applicant": doc.job_applicant})
		job_offer.status = "Accepted"
		job_offer.flags.ignore_mandatory = True
		job_offer.flags.ignore_permissions = True
		job_offer.save()

		msg = _("Updated the status of Job Offer {0} for the linked Job Applicant {1} to {2}").format(
			get_link_to_form("Job Offer", job_offer.name),
			frappe.bold(doc.job_applicant),
			frappe.bold(_("Accepted")),
		)
		if job_offer.docstatus == 0:
			msg += "<br>" + _("You may add additional details, if any, and submit the offer.")

		frappe.msgprint(msg)


def update_approver_role(doc, method=None):
	"""Adds relevant approver role for the user linked to the approver Employee"""
	leave_approver_user = resolve_employee_approver(doc.leave_approver)
	if leave_approver_user:
		user = frappe.get_doc("User", leave_approver_user)
		user.flags.ignore_permissions = True
		user.add_roles("Leave Approver")

	expense_approver_user = resolve_employee_approver(doc.expense_approver)
	if expense_approver_user:
		user = frappe.get_doc("User", expense_approver_user)
		user.flags.ignore_permissions = True
		user.add_roles("Expense Approver")


def auto_assign_leave_policy_on_activation(doc, method=None):
	"""When an Employee becomes Active, auto-assign the company's default Leave
	Policy. Submitting the Leave Policy Assignment cascades into Leave
	Allocations, so this collapses the leave-setup chain to zero clicks.

	Opt-in via HR Settings.auto_assign_leave_policy_on_activation, driven by the
	per-company Company.default_leave_policy / default_leave_period. Idempotent
	(skips if an overlapping assignment exists) and never blocks the Employee
	save — failures are logged, not raised.
	"""
	if doc.status != "Active":
		return
	if not cint(frappe.db.get_single_value("HR Settings", "auto_assign_leave_policy_on_activation")):
		return

	# Act only on the transition into Active, not on every later save.
	previous = doc.get_doc_before_save()
	if previous and previous.status == "Active":
		return

	if not doc.company:
		return
	leave_policy, leave_period = frappe.get_cached_value(
		"Company", doc.company, ["default_leave_policy", "default_leave_period"]
	)
	if not (leave_policy and leave_period):
		return

	period = frappe.db.get_value("Leave Period", leave_period, ["from_date", "to_date"], as_dict=True)
	if not period:
		return

	# Idempotent: skip if an overlapping (non-cancelled) assignment already exists.
	if frappe.db.exists(
		"Leave Policy Assignment",
		{
			"employee": doc.name,
			"docstatus": ("<", 2),
			"effective_from": ("<=", period.to_date),
			"effective_to": (">=", period.from_date),
		},
	):
		return

	from indian_hrms_compliance.hr.doctype.leave_policy_assignment.leave_policy_assignment import (
		create_assignment,
	)

	savepoint = "auto_leave_policy_assignment"
	try:
		frappe.db.savepoint(savepoint)
		assignment = create_assignment(
			doc.name,
			frappe._dict(
				assignment_based_on="Leave Period",
				leave_policy=leave_policy,
				leave_period=leave_period,
				effective_from=period.from_date,
				effective_to=period.to_date,
				carry_forward=0,
			),
		)
		assignment.submit()
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		frappe.log_error(
			title="Auto Leave Policy Assignment failed",
			message=f"Employee: {doc.name}\n{frappe.get_traceback()}",
		)
		return

	frappe.msgprint(
		_("Leave Policy {0} auto-assigned to {1} for {2}.").format(
			frappe.bold(leave_policy),
			frappe.bold(doc.employee_name or doc.name),
			frappe.bold(leave_period),
		),
		alert=True,
		indicator="green",
	)


@frappe.whitelist()
def get_employee_readiness(employee: str) -> dict:
	"""Full HR-setup readiness checklist for an Employee, grouped by category.

	Each item: label, done, critical, hint, route (Desk). `score.ready` is True
	only when every *critical* item is done. Drives the Employee form tab, the
	onboarding panel, and the cockpit's readiness aggregate.
	"""
	emp = frappe.db.get_value(
		"Employee",
		employee,
		[
			"name", "employee_name", "company", "user_id", "status",
			"pan_number", "aadhaar_last_4", "uan_number", "bank_ac_no", "ifsc_code",
			"reports_to", "leave_approver", "expense_approver", "default_shift", "holiday_list",
		],
		as_dict=True,
	)
	if not emp:
		return {}

	def has(doctype, filters):
		return bool(frappe.db.exists(doctype, filters))

	emp_filter = {"employee": employee, "docstatus": ("<", 2)}
	holiday_ok = bool(emp.holiday_list) or bool(
		frappe.db.get_value("Company", emp.company, "default_holiday_list")
	)
	policies_pending = frappe.db.count(
		"Employee Policy Acknowledgement", {"employee": employee, "status": "Pending"}
	)

	def item(label, done, critical=False, route=None, hint=""):
		return {"label": _(label), "done": bool(done), "critical": critical, "route": route, "hint": _(hint) if hint else ""}

	# Shift: default_shift OR a *submitted* Shift Assignment. The hint states
	# which one satisfied it, so a default-shift tick isn't mistaken for an
	# actual assignment.
	shift_assigned = has("Shift Assignment", {"employee": employee, "docstatus": 1})
	shift_done = bool(emp.default_shift) or shift_assigned
	if emp.default_shift:
		shift_hint = _("Default shift: {0}").format(emp.default_shift)
	elif shift_assigned:
		shift_hint = _("Shift assignment in place")
	else:
		shift_hint = _("Set a default shift or a shift assignment")

	emp_form = ["Form", "Employee", employee]
	categories = [
		{
			"name": _("Identity & Access"),
			"items": [
				item("User account linked", emp.user_id, True, emp_form, "Needed for ESS / PWA login"),
				item("PAN captured", emp.pan_number, True, emp_form, "Mandatory for TDS / Form 16"),
				item("Bank account & IFSC", emp.bank_ac_no and emp.ifsc_code, True, emp_form, "Needed for salary payout"),
				item("Aadhaar (last 4)", emp.aadhaar_last_4, False, emp_form),
				item("UAN captured", emp.uan_number, False, emp_form, "For PF / ECR"),
			],
		},
		{
			"name": _("Reporting & Approvers"),
			"items": [
				item("Reporting manager", emp.reports_to, False, emp_form),
				item("Leave approver", emp.leave_approver, True, emp_form),
				item("Expense approver", emp.expense_approver, False, emp_form),
			],
		},
		{
			"name": _("Leave & Holidays"),
			"items": [
				item("Leave Policy assigned", has("Leave Policy Assignment", emp_filter), True,
					 ["List", "Leave Policy Assignment", {"employee": employee}]),
				item("Leave allocated", has("Leave Allocation", {"employee": employee, "docstatus": 1}), False,
					 ["List", "Leave Allocation", {"employee": employee}]),
				item("Holiday List set", holiday_ok, True, emp_form, "On the employee or the company default"),
			],
		},
		{
			"name": _("Payroll"),
			"items": [
				item("Salary Structure assigned", has("Salary Structure Assignment", emp_filter), True,
					 ["List", "Salary Structure Assignment", {"employee": employee}]),
			],
		},
		{
			"name": _("Shift"),
			"items": [
				{
					"label": _("Shift configured"),
					"done": shift_done,
					"critical": False,
					"route": ["List", "Shift Assignment", {"employee": employee}],
					"hint": shift_hint,
				},
			],
		},
		{
			"name": _("Policies"),
			"items": [
				item("Company policies acknowledged", policies_pending == 0, True,
					 ["List", "Employee Policy Acknowledgement", {"employee": employee, "status": "Pending"}],
					 "No pending acknowledgements"),
			],
		},
	]

	flat = [i for c in categories for i in c["items"]]
	total = len(flat)
	done = sum(1 for i in flat if i["done"])
	critical_open = [i for i in flat if i["critical"] and not i["done"]]
	score = {
		"done": done,
		"total": total,
		"pct": round(done / total * 100) if total else 0,
		"ready": not critical_open,
		"critical_open": len(critical_open),
	}
	return {
		"employee": emp.name,
		"employee_name": emp.employee_name or employee,
		"company": emp.company,
		"status": emp.status,
		"score": score,
		"categories": categories,
		"items": flat,
	}


@frappe.whitelist()
def get_employee_readiness_summary(company: str | None = None) -> dict:
	"""Company-wide readiness aggregate (set-based, no per-employee loop).
	Returns how many Active employees are fully ready vs incomplete, and the
	count missing each critical check."""
	emp_filter = {"status": "Active"}
	if company:
		emp_filter["company"] = company

	emps = set(frappe.get_all("Employee", filters=emp_filter, pluck="name"))
	if not emps:
		return {"total": 0, "ready": 0, "incomplete": 0, "pct": 0, "missing": {}}

	def field_set(field):
		return emps & set(frappe.get_all("Employee", filters={**emp_filter, field: ("is", "set")}, pluck="name"))

	has_user = field_set("user_id")
	has_pan = field_set("pan_number")
	has_la = field_set("leave_approver")
	bank = field_set("bank_ac_no") & field_set("ifsc_code")

	if company and frappe.db.get_value("Company", company, "default_holiday_list"):
		has_holiday = set(emps)
	else:
		has_holiday = field_set("holiday_list")

	with_lpa = emps & set(frappe.get_all("Leave Policy Assignment", filters={"docstatus": ("<", 2)}, pluck="employee"))
	with_ssa = emps & set(frappe.get_all("Salary Structure Assignment", filters={"docstatus": ("<", 2)}, pluck="employee"))
	pending_ack = emps & set(frappe.get_all("Employee Policy Acknowledgement", filters={"status": "Pending"}, pluck="employee"))

	ready = has_user & has_pan & bank & has_la & has_holiday & with_lpa & with_ssa & (emps - pending_ack)
	missing = {
		"User login": len(emps - has_user),
		"PAN": len(emps - has_pan),
		"Bank details": len(emps - bank),
		"Leave approver": len(emps - has_la),
		"Holiday List": len(emps - has_holiday),
		"Leave Policy": len(emps - with_lpa),
		"Salary Structure": len(emps - with_ssa),
		"Policy acknowledgement": len(pending_ack),
	}
	return {
		"total": len(emps),
		"ready": len(ready),
		"incomplete": len(emps - ready),
		"pct": round(len(ready) / len(emps) * 100),
		"missing": missing,
	}


@frappe.whitelist()
def get_employee_setup_status(employee: str) -> dict:
	"""Back-compat flat shape for the onboarding panel — delegates to the full
	readiness checklist."""
	data = get_employee_readiness(employee)
	if not data:
		return {}
	return {
		"employee_name": data["employee_name"],
		"score": data["score"],
		"items": [{"label": i["label"], "done": i["done"], "route": i["route"]} for i in data["items"]],
	}


def update_approver_user_roles(doc, method=None):
	# doc is a User being saved; the approver fields now store Employee names, so
	# find Employees whose approver is one of this user's own Employee records.
	own_employees = frappe.get_all("Employee", filters={"user_id": doc.name}, pluck="name")
	if not own_employees:
		return

	approver_roles = set()
	if frappe.db.exists("Employee", {"leave_approver": ("in", own_employees)}):
		approver_roles.add("Leave Approver")

	if frappe.db.exists("Employee", {"expense_approver": ("in", own_employees)}):
		approver_roles.add("Expense Approver")

	if approver_roles:
		doc.append_roles(*approver_roles)


def update_employee_transfer(doc, method=None):
	"""Unsets Employee ID in Employee Transfer if doc is deleted"""
	if frappe.db.exists("Employee Transfer", {"new_employee_id": doc.name, "docstatus": 1}):
		emp_transfer = frappe.get_doc("Employee Transfer", {"new_employee_id": doc.name, "docstatus": 1})
		emp_transfer.db_set("new_employee_id", "")


@frappe.whitelist()
def get_timeline_data(doctype, name):
	"""Return timeline for attendance"""
	from frappe.desk.notifications import get_open_count

	out = {}

	open_count = get_open_count(doctype, name)
	out["count"] = open_count["count"]

	timeline_data = dict(
		frappe.db.sql(
			"""
			select unix_timestamp(attendance_date), count(*)
			from `tabAttendance` where employee=%s
			and attendance_date > date_sub(curdate(), interval 1 year)
			and status in ('Present', 'Half Day')
			group by attendance_date""",
			name,
		)
	)

	out["timeline_data"] = timeline_data
	return out


@frappe.whitelist()
def get_retirement_date(date_of_birth=None):
	if date_of_birth:
		try:
			retirement_age = cint(frappe.db.get_single_value("HR Settings", "retirement_age") or 60)
			dt = add_years(getdate(date_of_birth), retirement_age)
			return dt.strftime("%Y-%m-%d")
		except ValueError:
			# invalid date
			return
