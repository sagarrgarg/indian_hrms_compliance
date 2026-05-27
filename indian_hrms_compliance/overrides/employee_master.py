# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import re

import frappe
from frappe import _
from frappe.model.naming import set_name_by_naming_series
from frappe.query_builder import Interval
from frappe.query_builder.functions import Count, CurDate, UnixTimestamp
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


class EmployeeMaster(Employee):
	def autoname(self):
		naming_method = frappe.db.get_single_value("HR Settings", "emp_created_by")
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


def validate_onboarding_process(doc, method=None):
	"""Validates Employee Creation for linked Employee Onboarding"""
	job_applicant = doc.get("job_applicant")
	job_offer = doc.get("job_offer")

	filters = {"docstatus": 1, "boarding_status": ("!=", "Completed")}
	if job_offer:
		filters["job_offer"] = job_offer
	elif job_applicant:
		filters["job_applicant"] = job_applicant
	else:
		return

	employee_onboarding = frappe.get_all("Employee Onboarding", filters=filters)
	if employee_onboarding:
		onboarding = frappe.get_doc("Employee Onboarding", employee_onboarding[0].name)
		onboarding.validate_employee_creation()
		onboarding.db_set("employee", doc.name)


def publish_update(doc, method=None):
	import indian_hrms_compliance

	indian_hrms_compliance.refetch_resource("indian_hrms_compliance:employee", doc.user_id)


def update_job_applicant_and_offer(doc, method=None):
	"""Updates Job Applicant and Job Offer status as 'Accepted' and submits them"""
	job_applicant = doc.get("job_applicant")
	job_offer = get_linked_job_offer(doc, job_applicant)

	if job_offer and job_offer.status in ("Rejected", "Cancelled"):
		frappe.msgprint(
			_(
				"Linked Job Offer {0} was {1}. Please update the Job Offer status if this hire was intended."
			).format(get_link_to_form("Job Offer", job_offer.name), frappe.bold(_(job_offer.status))),
			title=_("Job Offer Status Not Updated"),
			indicator="orange",
		)
		return

	if job_applicant:
		applicant_status_before_change = frappe.db.get_value("Job Applicant", job_applicant, "status")
		if applicant_status_before_change != "Accepted":
			frappe.db.set_value("Job Applicant", job_applicant, "status", "Accepted")
			frappe.msgprint(
				_("Updated the status of linked Job Applicant {0} to {1}").format(
					get_link_to_form("Job Applicant", job_applicant), frappe.bold(_("Accepted"))
				)
			)

	if not job_offer or job_offer.status == "Accepted":
		return

	job_offer.status = "Accepted"
	job_offer.flags.ignore_mandatory = True
	job_offer.flags.ignore_permissions = True
	job_offer.save()

	msg = _("Updated the status of Job Offer {0} for {1} to {2}").format(
		get_link_to_form("Job Offer", job_offer.name),
		frappe.bold(job_offer.applicant_name),
		frappe.bold(_("Accepted")),
	)
	if job_offer.docstatus == 0:
		msg += "<br>" + _("You may add additional details, if any, and submit the offer.")

	frappe.msgprint(msg)


def get_linked_job_offer(doc, job_applicant: str | None):
	offer_name = doc.get("job_offer")
	if not offer_name and job_applicant:
		offer_name = frappe.db.get_value(
			"Job Offer", {"job_applicant": job_applicant, "docstatus": ["!=", 2]}, "name"
		)
	if not offer_name:
		return None

	job_offer = frappe.get_doc("Job Offer", offer_name)
	return None if job_offer.docstatus == 2 else job_offer


def update_approver_role(doc, method=None):
	"""Adds relevant approver role for the user linked to Employee"""
	if doc.leave_approver:
		user = frappe.get_doc("User", doc.leave_approver)
		user.flags.ignore_permissions = True
		user.add_roles("Leave Approver")

	if doc.expense_approver:
		user = frappe.get_doc("User", doc.expense_approver)
		user.flags.ignore_permissions = True
		user.add_roles("Expense Approver")


def update_approver_user_roles(doc, method=None):
	approver_roles = set()
	if frappe.db.exists("Employee", {"leave_approver": doc.name}):
		approver_roles.add("Leave Approver")

	if frappe.db.exists("Employee", {"expense_approver": doc.name}):
		approver_roles.add("Expense Approver")

	if approver_roles:
		doc.append_roles(*approver_roles)


def update_employee_transfer(doc, method=None):
	"""Unsets Employee ID in Employee Transfer if doc is deleted"""
	if frappe.db.exists("Employee Transfer", {"new_employee_id": doc.name, "docstatus": 1}):
		emp_transfer = frappe.get_doc("Employee Transfer", {"new_employee_id": doc.name, "docstatus": 1})
		emp_transfer.db_set("new_employee_id", "")


@frappe.whitelist()
def get_timeline_data(doctype: str, name: str) -> dict:
	"""Return timeline for attendance"""
	from frappe.desk.notifications import get_open_count

	out = {}

	frappe.has_permission(doctype, "read", name, throw=True)
	frappe.has_permission("Attendance", "read", throw=True)

	open_count = get_open_count(doctype, name)
	out["count"] = open_count["count"]

	Attendance = frappe.qb.DocType("Attendance")

	timeline_data = dict(
		(
			frappe.qb.from_(Attendance)
			.select(
				UnixTimestamp(Attendance.attendance_date),
				Count("*"),
			)
			.where(
				(Attendance.employee == name)
				& (Attendance.docstatus == 1)
				& (Attendance.attendance_date > (CurDate() - Interval(years=1)))
				& (Attendance.status.isin(["Present", "Half Day"]))
			)
			.groupby(Attendance.attendance_date)
		).run()
	)

	out["timeline_data"] = timeline_data
	return out


@frappe.whitelist()
def get_assignable_masters(company: str) -> dict[str, bool]:
	"""Return whether a submitted master exists for each gated Employee assignment action"""
	masters = {
		"Leave Policy": {"docstatus": 1},
		"Salary Structure": {"docstatus": 1, "is_active": "Yes", "company": company},
		"Shift Schedule": {"docstatus": 1},
	}

	return {
		doctype: bool(frappe.get_list(doctype, filters=filters, limit=1, pluck="name"))
		for doctype, filters in masters.items()
	}


@frappe.whitelist()
def get_retirement_date(date_of_birth: str | None = None):
	if date_of_birth:
		try:
			retirement_age = cint(frappe.db.get_single_value("HR Settings", "retirement_age") or 60)
			dt = add_years(getdate(date_of_birth), retirement_age)
			return dt.strftime("%Y-%m-%d")
		except ValueError:
			# invalid date
			return
