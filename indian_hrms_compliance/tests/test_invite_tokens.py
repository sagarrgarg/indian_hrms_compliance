# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Tests for the Employee Onboarding invite flows.

Current (v3): draft-backed opaque tokens — generating an invite creates a
Draft application holding ALL prefill server-side; the URL carries only a
random 48-char token (zero PII). Legacy signed tokens (v2 + pipe formats)
must keep verifying until they expire in the wild.
"""

import urllib.parse
from types import SimpleNamespace

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application import (
	_build_v2_token,
	_resolve_invite_draft,
	_sign,
	_verify_invite_token,
	generate_invite_link,
	generate_invite_link_full,
	get_invite_prefill,
)


def _company_and_designation():
	return (
		frappe.db.get_value("Company", {}, "name"),
		frappe.db.get_value("Designation", {}, "name"),
	)


def _token_from_url(url: str) -> str:
	q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
	return q["invite_token"][0]


REQUIRED_DOCS = [
	{"document_type": "PAN Card", "document": "/files/pan.pdf"},
	{"document_type": "Aadhaar Card", "document": "/files/aadhaar.pdf"},
	{"document_type": "Signed Offer Letter", "document": "/files/offer-signed.pdf"},
]


class TestDraftInvites(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company, cls.designation = _company_and_designation()
		if not (cls.company and cls.designation):
			raise frappe.tests.utils.unittest.SkipTest("Company + Designation required.")
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.db.rollback()

	def _generate(self, email="draft.invite@example.com", **kw):
		args = dict(
			first_name="Riya",
			last_name="Mehta",
			personal_email=email,
			target_company=self.company,
			target_designation=self.designation,
			validity_days=10,
			send_email=0,
		)
		args.update(kw)
		return generate_invite_link_full(**args)

	def test_url_carries_no_pii(self):
		out = self._generate()
		parsed = urllib.parse.urlparse(out["url"])
		q = urllib.parse.parse_qs(parsed.query)
		self.assertEqual(sorted(q.keys()), ["invite_token"], "URL must carry ONLY the opaque token")
		blob = urllib.parse.unquote(out["url"]).lower()
		for pii in ("riya", "mehta", "draft.invite@example.com", self.company.lower()):
			self.assertNotIn(pii, blob, f"PII '{pii}' leaked into the invite URL")
		# Opaque token, not a structured legacy token.
		token = q["invite_token"][0]
		self.assertNotIn("|", token)
		self.assertFalse(token.startswith("v2:"))
		self.assertGreaterEqual(len(token), 40)

	def test_generate_creates_draft_with_fields(self):
		out = self._generate()
		draft = frappe.get_doc("Employee Onboarding Application", out["draft"])
		self.assertEqual(draft.status, "Draft")
		self.assertEqual(draft.first_name, "Riya")
		self.assertEqual(draft.target_company, self.company)
		self.assertEqual(draft.target_designation, self.designation)
		self.assertEqual(draft.invite_email, "draft.invite@example.com")
		self.assertEqual(draft.invite_token, _token_from_url(out["url"]))

	def test_regenerate_refreshes_same_draft_and_kills_old_token(self):
		first = self._generate()
		old_token = _token_from_url(first["url"])
		second = self._generate(validity_days=5)
		self.assertEqual(first["draft"], second["draft"], "same email must reuse the draft")
		new_token = _token_from_url(second["url"])
		self.assertNotEqual(old_token, new_token)
		self.assertIsNone(_resolve_invite_draft(old_token), "old token must be dead")
		self.assertIsNotNone(_resolve_invite_draft(new_token))

	def test_prefill_endpoint_roundtrip_and_invalid_token(self):
		out = self._generate()
		token = _token_from_url(out["url"])
		pre = get_invite_prefill(token)
		self.assertEqual(pre["first_name"], "Riya")
		self.assertEqual(pre["personal_email"], "draft.invite@example.com")
		self.assertEqual(pre["target_company"], self.company)
		self.assertFalse(pre["has_offer_letter"])
		with self.assertRaises(frappe.exceptions.ValidationError):
			get_invite_prefill("x" * 48)

	def test_expired_draft_token_throws(self):
		out = self._generate()
		frappe.db.set_value(
			"Employee Onboarding Application",
			out["draft"],
			"invite_expires_on",
			add_days(getdate(), -1),
			update_modified=False,
		)
		token = _token_from_url(out["url"])
		with self.assertRaises(frappe.exceptions.ValidationError):
			get_invite_prefill(token)

	def test_submission_merges_draft_and_deletes_it(self):
		out = self._generate(email="merge.invite@example.com")
		token = _token_from_url(out["url"])
		frappe.local.request_ip = "203.0.113.99"
		doc = frappe.get_doc(
			{
				"doctype": "Employee Onboarding Application",
				"first_name": "Riya",
				"last_name": "Mehta",
				"personal_email": "merge.invite@example.com",
				"mobile_no": "9876543210",
				"date_of_birth": "1996-02-02",
				"gender": "Female",
				"pan_number": "MRGPD1111M",
				"aadhaar_number": "999999990019",
				"dpdp_consent": 1,
				"status": "Pending Verification",
				"invite_token": token,
				"is_fresher": 1,
				"documents": REQUIRED_DOCS,
			}
		).insert(ignore_permissions=True)

		self.assertEqual(doc.invited, 1)
		self.assertEqual(doc.target_company, self.company)
		self.assertEqual(doc.target_designation, self.designation)
		self.assertEqual(doc.invite_email, "merge.invite@example.com")
		# Draft must be absorbed (deleted) — one live record per candidate.
		self.assertFalse(
			frappe.db.exists("Employee Onboarding Application", out["draft"]),
			"placeholder draft should be deleted after submission",
		)

	def test_web_form_accept_path_absorbs_draft(self):
		"""End-to-end through the REAL guest pipeline (web_form.accept) — the
		exact path a browser takes. Regression pin for the bug where the
		hidden invite_token never reached the POST: token present ⇒ the new
		record is invited+merged and the placeholder Draft is deleted (never
		two records for one candidate)."""
		import json as _json

		from frappe.website.doctype.web_form.web_form import accept

		out = self._generate(email="acceptpath.invite@example.com")
		token = _token_from_url(out["url"])
		frappe.local.request_ip = "203.0.113.161"
		frappe.cache.delete_value("onboarding-rl:email:acceptpath.invite@example.com")
		frappe.cache.delete_value("onboarding-rl:ip:203.0.113.161")

		data = {
			"first_name": "Riya",
			"last_name": "Mehta",
			"personal_email": "acceptpath.invite@example.com",
			"mobile_no": "9876543210",
			"date_of_birth": "1996-02-02",
			"gender": "Female",
			"pan_number": "ACPPD6666A",
			"aadhaar_number": "999999990019",
			"dpdp_consent": 1,
			"invite_token": token,
			"is_fresher": 1,
			"documents": REQUIRED_DOCS,
		}
		frappe.set_user("Guest")
		try:
			doc = accept(web_form="employee-onboarding", data=_json.dumps(data))
		finally:
			frappe.set_user("Administrator")

		row = frappe.db.get_value(
			"Employee Onboarding Application",
			doc.get("name"),
			["invited", "target_company", "target_designation", "status"],
			as_dict=True,
		)
		self.assertEqual(row.invited, 1)
		self.assertEqual(row.target_company, self.company)
		self.assertEqual(row.target_designation, self.designation)
		self.assertEqual(row.status, "Pending Verification")
		self.assertFalse(
			frappe.db.exists("Employee Onboarding Application", out["draft"]),
			"draft must be absorbed — two records means the token was dropped",
		)
		frappe.cache.delete_value("onboarding-rl:email:acceptpath.invite@example.com")
		frappe.cache.delete_value("onboarding-rl:ip:203.0.113.161")

	def test_consent_user_agent_captured(self):
		out = self._generate(email="ua.invite@example.com")
		token = _token_from_url(out["url"])
		frappe.local.request_ip = "203.0.113.98"
		fake_request = SimpleNamespace(headers={"User-Agent": "KaamTest/1.0 (DPDP evidence)"})
		had_request = hasattr(frappe.local, "request")
		old_request = getattr(frappe.local, "request", None)
		frappe.local.request = fake_request
		try:
			doc = frappe.get_doc(
				{
					"doctype": "Employee Onboarding Application",
					"first_name": "Riya",
					"personal_email": "ua.invite@example.com",
					"mobile_no": "9876543210",
					"date_of_birth": "1996-02-02",
					"gender": "Female",
					"pan_number": "UAGPD2222U",
					"aadhaar_number": "999999990019",
					"dpdp_consent": 1,
					"status": "Pending Verification",
					"invite_token": token,
					"is_fresher": 1,
					"documents": REQUIRED_DOCS,
				}
			).insert(ignore_permissions=True)
		finally:
			if had_request:
				frappe.local.request = old_request
			else:
				del frappe.local.request
		self.assertEqual(doc.consent_user_agent, "KaamTest/1.0 (DPDP evidence)")
		self.assertEqual(doc.consent_ip, "203.0.113.98")
		self.assertTrue(doc.consent_timestamp)


class TestLegacyTokens(FrappeTestCase):
	"""Links issued before the draft flow must keep working until expiry."""

	def test_v2_roundtrip_and_tamper(self):
		payload = {"e": "legacy.v2@example.com", "x": str(add_days(getdate(), 5)), "f": "Leg", "c": "X", "d": "Y"}
		token = _build_v2_token(payload)
		parsed = _verify_invite_token(token)
		self.assertEqual(parsed["email"], "legacy.v2@example.com")
		self.assertEqual(parsed["first_name"], "Leg")
		flipped = "A" if token[5] != "A" else "B"
		self.assertIsNone(_verify_invite_token(token[:5] + flipped + token[6:]))

	def test_expired_v2_token_throws(self):
		token = _build_v2_token({"e": "expired@example.com", "x": "2020-01-01"})
		with self.assertRaises(frappe.exceptions.ValidationError):
			_verify_invite_token(token)

	def test_email_expiry_sig_roundtrip(self):
		frappe.set_user("Administrator")
		link = generate_invite_link("legacy@example.com", validity_days=10)
		token = _token_from_url(link["url"])
		self.assertEqual(token.count("|"), 2)
		payload = _verify_invite_token(token)
		self.assertEqual(payload["email"], "legacy@example.com")

	def test_old_email_sig_format_verifies(self):
		email = "very.old@example.com"
		token = f"{email}|{_sign(email)}"
		payload = _verify_invite_token(token)
		self.assertEqual(payload["email"], email)
		self.assertIsNone(payload["expires_on"])

	def test_bad_signature_rejected_for_each_format(self):
		self.assertIsNone(_verify_invite_token("foo@example.com|deadbeef"))
		self.assertIsNone(_verify_invite_token("foo@example.com|2099-01-01|deadbeef"))
		self.assertIsNone(_verify_invite_token("v2:abc.deadbeef"))
