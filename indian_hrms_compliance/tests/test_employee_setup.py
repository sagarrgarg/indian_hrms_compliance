# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Tests for the New Employee Setup orchestration
(indian_hrms_compliance.hr.employee_setup.setup_new_employee).

Covers the guided-onboarding wiring added for the convert-from-application flow:
  * job_applicant threaded onto the Employee (and the Applicant marked Accepted)
  * probation vs. confirmed paths reflected on confirmation_status
  * Leave Policy assigned when chosen
  * only the curated policy subset gets acknowledgements (the activation-time
    blanket auto-enrol is suppressed during setup)

setup_new_employee() commits at the end, so each test patches frappe.db.commit
to a no-op and relies on FrappeTestCase rollback for isolation.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, getdate


def _first(doctype, filters=None):
	return frappe.db.get_value(doctype, filters or {}, "name")


def _make_leave_policy():
	leave_type = _first("Leave Type") or frappe.get_doc(
		{"doctype": "Leave Type", "leave_type_name": "NES Test Leave", "max_leaves_allowed": 12}
	).insert(ignore_permissions=True).name
	policy = frappe.get_doc(
		{
			"doctype": "Leave Policy",
			"title": "NES Test Leave Policy",
			"leave_policy_details": [{"leave_type": leave_type, "annual_allocation": 12}],
		}
	).insert(ignore_permissions=True)
	policy.submit()
	frappe.db.commit()
	return policy.name


def _make_shift():
	shift = frappe.get_doc({"doctype": "Shift Type", "start_time": "09:00:00", "end_time": "18:00:00"})
	shift.insert(ignore_permissions=True, set_name="NES Test Shift")
	frappe.db.commit()
	return shift.name


class TestNewEmployeeSetup(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = _first("Company")
		cls.gender = _first("Gender")
		if not (cls.company and cls.gender):
			raise frappe.tests.utils.unittest.SkipTest("Company + Gender required.")
		frappe.set_user("Administrator")
		# Branch is mandatory on an active Employee.
		cls.branch = "NES Test Branch"
		if not frappe.db.exists("Branch", cls.branch):
			frappe.get_doc({"doctype": "Branch", "branch": cls.branch}).insert(ignore_permissions=True)
		# Leave Policy and Shift are mandatory on the setup page; use the site's own
		# or create minimal ones so the tests run on an empty test site too.
		cls.leave_policy = _first("Leave Policy", {"docstatus": 1}) or _make_leave_policy()
		cls.shift = _first("Shift Type") or _make_shift()

	def tearDown(self):
		frappe.db.rollback()

	def _data(self, **kw):
		data = dict(
			first_name="Setup",
			last_name="Tester",
			company=self.company,
			branch=self.branch,
			leave_policy=self.leave_policy,
			default_shift=self.shift,
			gender=self.gender,
			date_of_birth="1995-05-05",
			date_of_joining="2026-01-01",
			pan_number="ABCPK1234K",
			create_user=0,
			send_welcome_email=0,
			create_user_permission=0,
		)
		data.update(kw)
		return data

	def _run(self, **kw):
		# setup_new_employee() commits; keep its work inside the test transaction.
		from indian_hrms_compliance.hr.employee_setup import setup_new_employee

		with patch("frappe.db.commit"):
			return setup_new_employee(self._data(**kw))

	# ---- confirmation / probation -------------------------------------

	def test_probation_path_sets_status_and_schedule(self):
		res = self._run(place_on_probation=1, probation_months=3)
		emp = frappe.get_doc("Employee", res["employee"])
		self.assertEqual(emp.confirmation_status, "Probation")
		# Stays Active so payroll / attendance / leave keep working on probation.
		self.assertEqual(emp.status, "Active")
		self.assertEqual(
			getdate(emp.scheduled_confirmation_date),
			add_months(getdate("2026-01-01"), 3),
		)

	def test_confirmed_path_sets_final_confirmation_date(self):
		res = self._run(final_confirmation_date="2026-01-15")
		emp = frappe.get_doc("Employee", res["employee"])
		self.assertEqual(emp.confirmation_status, "Confirmed")
		self.assertEqual(getdate(emp.final_confirmation_date), getdate("2026-01-15"))

	def test_no_confirmation_input_leaves_status_unset(self):
		res = self._run()
		emp = frappe.get_doc("Employee", res["employee"])
		self.assertIn(emp.confirmation_status, (None, ""))

	# ---- job applicant link + cascade ---------------------------------

	def test_job_applicant_linked_and_marked_accepted(self):
		designation = _first("Designation")
		if not designation:
			self.skipTest("Designation required to create a Job Applicant.")
		applicant = frappe.get_doc(
			{
				"doctype": "Job Applicant",
				"applicant_name": "Cascade Candidate",
				"email_id": "cascade.candidate@example.com",
				"designation": designation,
				"status": "Open",
			}
		).insert(ignore_permissions=True)

		res = self._run(job_applicant=applicant.name)
		emp = frappe.get_doc("Employee", res["employee"])
		self.assertEqual(emp.job_applicant, applicant.name)
		# after_insert cascade flips the applicant to Accepted.
		self.assertEqual(
			frappe.db.get_value("Job Applicant", applicant.name, "status"), "Accepted"
		)

	# ---- curated policy acknowledgements ------------------------------

	def _make_policy(self, title):
		return frappe.get_doc(
			{
				"doctype": "HRMS Policy",
				"policy_name": title,
				"policy_category": "Other",
				"company": self.company,
				"version": "1.0",
				"status": "Active",
				"effective_date": "2026-01-01",
				"requires_acknowledgement": 1,
			}
		).insert(ignore_permissions=True)

	def _has_ack(self, employee, policy):
		return bool(
			frappe.db.exists(
				"Employee Policy Acknowledgement", {"employee": employee, "policy": policy}
			)
		)

	def test_only_selected_policies_get_acknowledgements(self):
		chosen = self._make_policy("NES Chosen Policy")
		skipped = self._make_policy("NES Skipped Policy")

		emp = self._run(policies_to_ack=[chosen.name])["employee"]
		self.assertTrue(self._has_ack(emp, chosen.name), "chosen policy must enrol")
		self.assertFalse(
			self._has_ack(emp, skipped.name),
			"unchosen active policy must NOT enrol (selective enrol + blanket suppressed)",
		)

	def test_no_policies_selected_suppresses_blanket_enrolment(self):
		policy = self._make_policy("NES Blanket Policy")
		emp = self._run(policies_to_ack=[])["employee"]
		self.assertFalse(
			self._has_ack(emp, policy.name),
			"empty selection must not trigger the activation blanket auto-enrol",
		)

	# ---- leave policy assignment --------------------------------------

	def test_leave_policy_assignment_created_when_chosen(self):
		leave_policy = self.leave_policy
		emp = self._run(leave_policy=leave_policy)["employee"]
		lpa = frappe.db.get_value(
			"Leave Policy Assignment",
			{"employee": emp, "leave_policy": leave_policy},
			["name", "assignment_based_on", "docstatus"],
			as_dict=True,
		)
		self.assertTrue(lpa, "a Leave Policy Assignment should be created for the employee")
		self.assertEqual(lpa.assignment_based_on, "Joining Date")
		self.assertEqual(lpa.docstatus, 1, "the assignment should be submitted")

	# ---- branch --------------------------------------------------------

	def test_branch_is_set_on_employee(self):
		emp = self._run()["employee"]
		self.assertEqual(frappe.db.get_value("Employee", emp, "branch"), self.branch)

	def test_missing_branch_is_rejected_before_anything_is_created(self):
		before = frappe.db.count("Employee")
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._run(branch=None)
		self.assertIn("Branch", str(ctx.exception))
		self.assertEqual(frappe.db.count("Employee"), before)

	def test_salary_structure_of_another_branch_is_rejected(self):
		# Only the structure's Applicable Branches rows are read by the check.
		structure = "NES Branch-Locked Structure"
		other = "NES Other Branch"
		if not frappe.db.exists("Branch", other):
			frappe.get_doc({"doctype": "Branch", "branch": other}).insert(ignore_permissions=True)
		# Restrict the structure to the other branch only.
		frappe.get_doc(
			{
				"doctype": "Salary Structure Branch",
				"parent": structure,
				"parenttype": "Salary Structure",
				"parentfield": "applicable_branches",
				"branch": other,
			}
		).db_insert()
		before = frappe.db.count("Employee")
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._run(salary_structure=structure)
		self.assertIn("not applicable", str(ctx.exception))
		self.assertEqual(frappe.db.count("Employee"), before)

	def test_application_target_branch_prefills_setup(self):
		from indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application import (
			get_application_for_setup,
		)

		name = frappe.generate_hash(length=10)
		frappe.get_doc(
			{
				"doctype": "Employee Onboarding Application",
				"name": name,
				"first_name": "Prefill",
				"personal_email": "prefill.branch@example.com",
				"status": "Verified",
				"target_company": self.company,
				"target_branch": self.branch,
			}
		).db_insert()
		self.assertEqual(get_application_for_setup(name)["branch"], self.branch)
