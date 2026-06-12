# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Guest rate-limit semantics for the public onboarding form.

The contract under test:
  * Failed validation attempts must NOT consume the daily allowance
    (counters move in after_insert, checks happen in before_insert).
  * A successful submission consumes it; a second public submission from the
    same email the same day is blocked.
  * An invited candidate (live draft token matching their email) BYPASSES the
    per-email throttle entirely — HR's invite is explicit authorization.
"""

import urllib.parse

import frappe
from frappe.exceptions import ValidationError
from frappe.tests.utils import FrappeTestCase

from indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application import (
	generate_invite_link_full,
)

REQUIRED_DOCS = [
	{"document_type": "PAN Card", "document": "/files/pan.pdf"},
	{"document_type": "Aadhaar Card", "document": "/files/aadhaar.pdf"},
	{"document_type": "Signed Offer Letter", "document": "/files/offer-signed.pdf"},
]


def _clear_keys(email, ip="203.0.113.150"):
	frappe.cache.delete_value(f"onboarding-rl:email:{email}")
	frappe.cache.delete_value(f"onboarding-rl:ip:{ip}")


def _payload(email, pan, **kw):
	d = {
		"doctype": "Employee Onboarding Application",
		"first_name": "Rate",
		"last_name": "Limit",
		"personal_email": email,
		"mobile_no": "9876543210",
		"date_of_birth": "1995-03-03",
		"gender": "Male",
		"pan_number": pan,
		"aadhaar_number": "999999990019",
		"dpdp_consent": 1,
		"status": "Pending Verification",
		"is_fresher": 1,
		"documents": REQUIRED_DOCS,
	}
	d.update(kw)
	return d


class TestGuestRateLimit(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Guest")
		frappe.local.request_ip = "203.0.113.150"

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_failed_validation_does_not_burn_allowance(self):
		email = "burn.test@example.com"
		_clear_keys(email)
		# Attempt 1: missing documents → validation throws.
		with self.assertRaises(ValidationError):
			frappe.get_doc(_payload(email, "RLAPD1111R", documents=[], is_fresher=0)).insert(
				ignore_permissions=True
			)
		# Attempt 2 (fixed): must succeed — the failed try must not count.
		doc = frappe.get_doc(_payload(email, "RLAPD1111R")).insert(ignore_permissions=True)
		self.assertTrue(doc.name)
		_clear_keys(email)

	def test_second_public_submission_same_email_blocked(self):
		email = "twice.test@example.com"
		_clear_keys(email)
		frappe.get_doc(_payload(email, "RLBPD2222R")).insert(ignore_permissions=True)
		with self.assertRaises(ValidationError) as ctx:
			frappe.get_doc(_payload(email, "RLCPD3333R")).insert(ignore_permissions=True)
		self.assertIn("already", str(ctx.exception).lower())
		_clear_keys(email)

	def test_invited_submission_bypasses_email_throttle(self):
		email = "invited.bypass@example.com"
		_clear_keys(email)
		# Pre-exhaust the allowance, as if a public submission happened today.
		frappe.cache.set_value(f"onboarding-rl:email:{email}", 99, expires_in_sec=600)

		# HR issues an invite (draft + opaque token) for the same email.
		frappe.set_user("Administrator")
		out = generate_invite_link_full(
			first_name="Invited",
			personal_email=email,
			target_company=frappe.db.get_value("Company", {}, "name"),
			target_designation=frappe.db.get_value("Designation", {}, "name"),
			validity_days=5,
			send_email=0,
		)
		token = urllib.parse.parse_qs(urllib.parse.urlparse(out["url"]).query)["invite_token"][0]
		frappe.set_user("Guest")
		frappe.local.request_ip = "203.0.113.150"

		# Despite the exhausted counter, the invited submission goes through.
		doc = frappe.get_doc(
			_payload(email, "RLDPD4444R", invite_token=token)
		).insert(ignore_permissions=True)
		self.assertEqual(doc.invited, 1)
		_clear_keys(email)

	def test_ip_limit_still_applies_to_invited(self):
		"""The invite bypass is email-scoped only — the per-IP abuse cap holds."""
		email = "ip.cap@example.com"
		ip = "203.0.113.151"
		frappe.local.request_ip = ip
		frappe.cache.delete_value(f"onboarding-rl:email:{email}")
		frappe.cache.set_value(f"onboarding-rl:ip:{ip}", 99, expires_in_sec=600)

		frappe.set_user("Administrator")
		out = generate_invite_link_full(
			first_name="Capped",
			personal_email=email,
			target_company=frappe.db.get_value("Company", {}, "name"),
			target_designation=frappe.db.get_value("Designation", {}, "name"),
			validity_days=5,
			send_email=0,
		)
		token = urllib.parse.parse_qs(urllib.parse.urlparse(out["url"]).query)["invite_token"][0]
		frappe.set_user("Guest")
		frappe.local.request_ip = ip

		with self.assertRaises(ValidationError):
			frappe.get_doc(_payload(email, "RLEPD5555R", invite_token=token)).insert(
				ignore_permissions=True
			)
		frappe.cache.delete_value(f"onboarding-rl:ip:{ip}")
