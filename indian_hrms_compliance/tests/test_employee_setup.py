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


class TestNewEmployeeSetup(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = _first("Company")
		cls.gender = _first("Gender")
		if not (cls.company and cls.gender):
			raise frappe.tests.utils.unittest.SkipTest("Company + Gender required.")
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.db.rollback()

	def _data(self, **kw):
		data = dict(
			first_name="Setup",
			last_name="Tester",
			company=self.company,
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
		leave_policy = _first("Leave Policy")
		if not leave_policy:
			self.skipTest("A configured Leave Policy is required for this test.")
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
