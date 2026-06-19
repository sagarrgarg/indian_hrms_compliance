# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Let Guest users upload files, so the PUBLIC Employee Onboarding web form can
accept document attachments (PAN / Aadhaar / Previous Payslip / signed Offer
Letter / photo).

Frappe gates EVERY guest upload behind one site-wide System Setting,
``allow_guests_to_upload_files``. With it off, ``frappe.handler.upload_file``
raises ``PermissionError`` the instant a guest clicks Upload — the candidate
sees an error or the upload control just hangs. The onboarding form is an
anonymous web form (login_required=0), so this flag must be on for it to work.

Idempotent + defensive (see the frappe-framework skill): guards the field's
existence, only flips a blank/0 value to 1 (never stomps an operator who already
turned it on), and is safe to re-run. Guests remain restricted by Frappe core to
JPG/PNG/GIF/PDF/TXT/CSV/MS-office MIME types and the site's max file size, so
enabling this does not let arbitrary content in.
"""

import frappe


def execute():
	# System Settings is core, but guard anyway — a missing field must be a
	# no-op, never a get_single_value crash that aborts the whole migrate.
	if not frappe.get_meta("System Settings").has_field("allow_guests_to_upload_files"):
		return

	if frappe.db.get_single_value("System Settings", "allow_guests_to_upload_files"):
		return  # already enabled (by us before, or by the operator) — leave it.

	frappe.db.set_single_value("System Settings", "allow_guests_to_upload_files", 1)
	frappe.clear_cache(doctype="System Settings")
	print("  Enabled allow_guests_to_upload_files so the public onboarding form can accept document uploads")
