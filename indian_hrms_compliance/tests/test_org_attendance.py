# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Tests for get_org_attendance_today buckets, scope, dual-mode, and authorization."""

from frappe.utils import add_days, getdate

import frappe
from frappe.tests.utils import FrappeTestCase

from indian_hrms_compliance.api import get_org_attendance_today


class TestOrgAttendanceTodayMode(FrappeTestCase):
	def test_admin_gets_all_scope(self):
		frappe.set_user("Administrator")
		out = get_org_attendance_today()
		# Admin has System Manager → scope='all' branch.
		self.assertEqual(out["scope"], "all")
		self.assertEqual(out["mode"], "today")
		self.assertIn("counts", out)
		for bucket in ("in_now", "out", "on_leave", "not_yet_in"):
			self.assertIn(bucket, out["counts"])
			self.assertIsInstance(out[bucket], list)

	def test_counts_sum_equals_total(self):
		frappe.set_user("Administrator")
		out = get_org_attendance_today()
		counts = out["counts"]
		self.assertEqual(
			counts["in_now"] + counts["out"] + counts["on_leave"] + counts["not_yet_in"],
			counts["total"],
			"today's buckets must partition the active employee set",
		)

	def test_explicit_all_scope_for_admin(self):
		frappe.set_user("Administrator")
		out = get_org_attendance_today(scope="all")
		self.assertEqual(out["scope"], "all")
		self.assertEqual(out["mode"], "today")

	def test_for_date_today_returns_today_mode(self):
		frappe.set_user("Administrator")
		out = get_org_attendance_today(for_date=str(getdate()))
		self.assertEqual(out["mode"], "today")

	def test_future_date_falls_back_to_today(self):
		frappe.set_user("Administrator")
		future = str(add_days(getdate(), 7))
		out = get_org_attendance_today(for_date=future)
		# Future dates make no sense → silently clamp to today, no throw.
		self.assertEqual(out["mode"], "today")
		self.assertEqual(out["for_date"], str(getdate()))


class TestOrgAttendancePastMode(FrappeTestCase):
	def test_yesterday_returns_past_mode_shape(self):
		frappe.set_user("Administrator")
		yesterday = str(add_days(getdate(), -1))
		out = get_org_attendance_today(for_date=yesterday)
		self.assertEqual(out["mode"], "past")
		for bucket in ("present", "absent", "on_leave", "not_marked"):
			self.assertIn(bucket, out["counts"])
			self.assertIsInstance(out[bucket], list)

	def test_past_buckets_partition_active_set(self):
		frappe.set_user("Administrator")
		yesterday = str(add_days(getdate(), -1))
		out = get_org_attendance_today(for_date=yesterday)
		counts = out["counts"]
		self.assertEqual(
			counts["present"] + counts["absent"] + counts["on_leave"] + counts["not_marked"],
			counts["total"],
			"past buckets must partition the active employee set",
		)

	def test_team_scope_falls_through_to_none_when_no_reports(self):
		# Find a user with NO direct reports and no HR role.
		users = frappe.db.sql(
			"""
			SELECT u.name
			FROM `tabUser` u
			WHERE u.enabled = 1
			  AND u.name NOT IN ('Administrator', 'Guest')
			  AND NOT EXISTS (
			    SELECT 1 FROM `tabHas Role` r
			    WHERE r.parent = u.name
			      AND r.role IN ('HR Manager', 'HR User', 'System Manager')
			  )
			  AND NOT EXISTS (
			    SELECT 1 FROM `tabEmployee` me
			    JOIN `tabEmployee` rep ON rep.reports_to = me.name
			    WHERE me.user_id = u.name
			      AND me.status = 'Active'
			      AND rep.status = 'Active'
			  )
			LIMIT 1
			""",
			as_dict=True,
		)
		if not users:
			self.skipTest("No non-HR, non-manager user available.")
		frappe.set_user(users[0]["name"])
		try:
			out = get_org_attendance_today(scope="team")
			self.assertEqual(out["scope"], "none")
			self.assertEqual(out["in_now"], [])
		finally:
			frappe.set_user("Administrator")

	def test_company_filter(self):
		frappe.set_user("Administrator")
		any_company = frappe.db.get_value("Company", {}, "name")
		if not any_company:
			self.skipTest("No Company on site.")
		out = get_org_attendance_today(company=any_company)
		# Every employee returned should belong to the filtered company.
		all_buckets = out["in_now"] + out["out"] + out["on_leave"] + out["not_yet_in"]
		for card in all_buckets:
			self.assertEqual(card["company"], any_company)
