"""Repair Attendance Request `status` for rows the first backfill missed.

`backfill_attendance_request_status` only touched rows whose status was NULL or
''. But the `status` Custom Field carries `default: "Open"`, and when the column
was added the database back-filled EVERY existing row with 'Open' — so the guard
matched nothing and already-submitted requests were left saying "Open"
(observed: 98 submitted requests stuck at Open on a live site).

This patch reconciles status with docstatus:
  docstatus 1 (submitted) → Approved
  docstatus 2 (cancelled) → Cancelled
  docstatus 0 (draft)     → Open, but only when blank

It deliberately never overwrites a *decided* draft — Rejected / Needs
Clarification are docstatus 0 with a non-blank status, so they are left alone.
Idempotent: re-running changes nothing once reconciled.
"""

import frappe


def execute():
	if not frappe.db.table_exists("Attendance Request"):
		return

	# Self-contained: don't assume the field-creating hook/patch has run.
	if not frappe.get_meta("Attendance Request").has_field("status"):
		from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

		from indian_hrms_compliance.setup import get_custom_fields

		fields = get_custom_fields().get("Attendance Request")
		if not fields:
			return
		create_custom_fields({"Attendance Request": fields}, ignore_validate=True)
		frappe.clear_cache(doctype="Attendance Request")

	if not frappe.get_meta("Attendance Request").has_field("status"):
		return

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
