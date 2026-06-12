# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Smoke tests for the PWA Approvals inbox providers + the realtime helpers.

These tests are intentionally shape-only: each provider must return a list of
dicts with the documented keys, summary must include all categories, and the
realtime helpers must not raise."""

import frappe
from frappe.tests.utils import FrappeTestCase

from indian_hrms_compliance.api import (
	_APPROVAL_CATEGORIES,
	_APPROVAL_PROVIDERS,
	_INBOX_CACHE_KEYS,
	_REQUESTER_CACHE_KEYS_BY_DOCTYPE,
	_broadcast_hr_inbox_refresh,
	_pwa_refetch,
	get_approvals_summary,
	get_pending_approvals,
	publish_org_attendance_refetch,
)

REQUIRED_ITEM_KEYS = {"doctype", "name", "category", "title", "employee_name", "date", "action_type"}


class TestInboxProviders(FrappeTestCase):
	def test_every_provider_returns_list(self):
		"""All 10 providers are callable and return a list (possibly empty)."""
		for provider in _APPROVAL_PROVIDERS:
			rows = provider("Administrator") or []
			self.assertIsInstance(rows, list, f"{provider.__name__} did not return a list")

	def test_every_row_has_required_keys(self):
		"""Every row returned by any provider must conform to the inbox item shape."""
		for provider in _APPROVAL_PROVIDERS:
			rows = provider("Administrator") or []
			for row in rows:
				missing = REQUIRED_ITEM_KEYS - set(row.keys())
				self.assertFalse(
					missing,
					f"{provider.__name__} returned row missing keys {missing}: {row}",
				)
				self.assertIn(row["category"], _APPROVAL_CATEGORIES)

	def test_summary_includes_every_category(self):
		summary = get_approvals_summary()
		for cat in _APPROVAL_CATEGORIES:
			self.assertIn(cat, summary, f"summary missing category {cat}")
		self.assertIn("total", summary)

	def test_get_pending_approvals_sorts_newest_first(self):
		items = get_pending_approvals()
		dates = [(i.get("date") or "") for i in items]
		# Sort is reverse; verify by comparing each pair.
		for a, b in zip(dates, dates[1:]):
			self.assertGreaterEqual(a, b, "items not in date desc order")


class TestRealtimeHelpers(FrappeTestCase):
	def test_inbox_cache_keys_constants(self):
		"""The two inbox cache keys must match what socket.js looks for."""
		self.assertEqual(len(_INBOX_CACHE_KEYS), 2)
		for k in _INBOX_CACHE_KEYS:
			self.assertTrue(k.startswith("indian_hrms_compliance:"))

	def test_requester_cache_keys_map_no_typos(self):
		"""Every doctype in the inbox should have a row in the requester map
		(possibly an empty tuple if no employee-side resource exists)."""
		from indian_hrms_compliance.api import _APPROVAL_DOCTYPES

		for dt in _APPROVAL_DOCTYPES:
			self.assertIn(
				dt,
				_REQUESTER_CACHE_KEYS_BY_DOCTYPE,
				f"_REQUESTER_CACHE_KEYS_BY_DOCTYPE missing entry for {dt}",
			)
			# Every key inside must be a fully-qualified cache key.
			for k in _REQUESTER_CACHE_KEYS_BY_DOCTYPE[dt]:
				self.assertTrue(k.startswith("indian_hrms_compliance:"), f"bad key {k}")

	def test_pwa_refetch_does_not_raise(self):
		"""Even if no socket-server is up in test, the helper must swallow errors."""
		try:
			_pwa_refetch("indian_hrms_compliance:test", user="Administrator")
			_pwa_refetch(["indian_hrms_compliance:a", "indian_hrms_compliance:b"])
		except Exception as e:
			self.fail(f"_pwa_refetch raised: {e}")

	def test_broadcast_hr_inbox_refresh_does_not_raise(self):
		try:
			_broadcast_hr_inbox_refresh()
		except Exception as e:
			self.fail(f"_broadcast_hr_inbox_refresh raised: {e}")

	def _reset_org_att_flags(self):
		from indian_hrms_compliance.api import _ORG_ATT_RECIPIENTS_FLAG, _ORG_ATT_REFETCH_FLAG

		for flag in (_ORG_ATT_REFETCH_FLAG, _ORG_ATT_RECIPIENTS_FLAG):
			if hasattr(frappe.local, flag):
				delattr(frappe.local, flag)

	def test_publish_org_attendance_refetch_does_not_raise(self):
		try:
			publish_org_attendance_refetch()
		except Exception as e:
			self.fail(f"publish_org_attendance_refetch raised: {e}")
		finally:
			self._reset_org_att_flags()

	def test_publish_org_attendance_refetch_debounces(self):
		"""Second call within the same request must not publish anything more
		(even though the first call may publish to many recipients)."""
		captured = []
		orig = frappe.publish_realtime

		def fake(event=None, message=None, **kw):
			captured.append((event, message))

		frappe.publish_realtime = fake
		try:
			self._reset_org_att_flags()
			publish_org_attendance_refetch()
			first_count = len(captured)
			publish_org_attendance_refetch()  # Debounced — no new captures.
			second_count = len(captured) - first_count
		finally:
			frappe.publish_realtime = orig
			self._reset_org_att_flags()
		self.assertEqual(second_count, 0, "debounce did not suppress second publish")

	def test_publish_org_attendance_refetch_fans_out_to_recipients(self):
		"""First call publishes to >= 1 user (admin counts as System Manager)."""
		captured_users = []
		orig = frappe.publish_realtime

		def fake(event=None, message=None, user=None, **kw):
			if event == "indian_hrms_compliance:refetch_resource":
				captured_users.append(user)

		frappe.publish_realtime = fake
		try:
			self._reset_org_att_flags()
			publish_org_attendance_refetch()
		finally:
			frappe.publish_realtime = orig
			self._reset_org_att_flags()
		self.assertGreaterEqual(len(captured_users), 1, "no recipients fanned out")
		# Every publish must be targeted (no user=None broadcast slips through).
		self.assertNotIn(None, captured_users, "broadcast user=None slipped through")
