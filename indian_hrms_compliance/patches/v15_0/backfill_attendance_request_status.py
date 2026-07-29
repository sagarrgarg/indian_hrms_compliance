"""Backfill the new Attendance Request `status` field on existing rows.

Attendance Request historically had no approval status (draft → submit only).
We added a `status` Custom Field (Open / Approved / Rejected / Needs
Clarification / Cancelled) so rejections/clarifications can be recorded durably
instead of the row being hard-deleted.

A Custom Field `default` only applies to NEW documents — existing rows read as
NULL — so map them from docstatus here. Self-contained + idempotent: it creates
the field itself (does not assume after_migrate's sync ran first) and only
writes rows whose status is still blank.
"""

import frappe

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	# Doctype/table may not exist on a site that doesn't have the HR app rows yet.
	if not frappe.db.table_exists("Attendance Request"):
		return

	# Self-contained: ensure the Custom Field exists before backfilling. Patches
	# (post_model_sync) run BEFORE the after_migrate sync_custom_fields hook, so
	# on the very first migrate the column would otherwise be missing.
	if not frappe.get_meta("Attendance Request").has_field("status"):
		from indian_hrms_compliance.setup import get_custom_fields

		fields = get_custom_fields().get("Attendance Request")
		if not fields:
			return
		create_custom_fields({"Attendance Request": fields}, ignore_validate=True)
		frappe.clear_cache(doctype="Attendance Request")

	if not frappe.get_meta("Attendance Request").has_field("status"):
		# Field still absent (should never happen) — bail rather than crash.
		return

	# docstatus → 1 = Approved (submitted), 2 = Cancelled, 0 = Open (pending).
	#
	# NOTE: the guard must also catch 'Open', not just NULL/''. The status field
	# carries default "Open", so adding the column back-fills every existing row
	# with 'Open' — a NULL-only guard silently matches nothing and leaves
	# submitted requests reading "Open". Decided drafts (Rejected / Needs
	# Clarification) are docstatus 0 with a non-blank status and are never
	# touched. Idempotent.
	frappe.db.sql(
		"""
		UPDATE `tabAttendance Request`
		SET status = CASE docstatus
			WHEN 1 THEN 'Approved'
			WHEN 2 THEN 'Cancelled'
			ELSE 'Open'
		END
		WHERE
			(docstatus IN (1, 2) AND (status IS NULL OR status IN ('', 'Open')))
			OR (docstatus = 0 AND (status IS NULL OR status = ''))
		"""
	)
