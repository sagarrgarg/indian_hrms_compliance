# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document


class GigPlatformWorker(Document):
	def autoname(self):
		"""Sanitize worker_id for safe naming (alnum + dash/underscore only)."""
		if not self.worker_id:
			return
		sanitized = re.sub(r"[^A-Za-z0-9_\-]", "-", self.worker_id.strip())
		if sanitized != self.worker_id:
			self.worker_id = sanitized
		# Frappe's format autoname will use {worker_id}

	def validate(self):
		self._normalise_aadhaar()
		self._validate_aadhaar()
		self._validate_pan()
		self._validate_uan()
		self._validate_engagement_dates()

	def _normalise_aadhaar(self):
		if self.aadhaar_number:
			self.aadhaar_number = re.sub(r"\D", "", self.aadhaar_number)
			# Auto-derive the legacy last-4 column from the full number so the
			# DPDP audit + UAN-Aadhaar linkage reports keep working unchanged.
			self.aadhaar_last_4 = self.aadhaar_number[-4:]

	def _validate_aadhaar(self):
		from indian_hrms_compliance.overrides.employee_master import (
			AADHAAR_FULL_RE,
			verhoeff_check_aadhaar,
		)

		if self.aadhaar_number:
			if not AADHAAR_FULL_RE.match(self.aadhaar_number):
				frappe.throw(_("Aadhaar must be exactly 12 digits and start with 2-9."))
			if not verhoeff_check_aadhaar(self.aadhaar_number):
				frappe.throw(_("Aadhaar checksum failed — please re-check the number."))
		elif self.aadhaar_last_4 and not re.fullmatch(r"\d{4}", self.aadhaar_last_4):
			frappe.throw(_("Aadhaar (last 4) must be exactly 4 digits."))

	def _validate_pan(self):
		if self.pan_number and not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", self.pan_number):
			frappe.msgprint(
				_("PAN format looks invalid (expected ABCDE1234F)."),
				indicator="orange",
				title=_("PAN Format"),
			)

	def _validate_uan(self):
		if self.uan and not re.fullmatch(r"\d{12}", self.uan):
			frappe.msgprint(
				_("UAN should be a 12-digit number."),
				indicator="orange",
				title=_("UAN Format"),
			)

	def _validate_engagement_dates(self):
		from frappe.utils import getdate

		if self.engagement_end and self.engagement_start:
			if getdate(self.engagement_end) < getdate(self.engagement_start):
				frappe.throw(_("Engagement End cannot be before Engagement Start."))
