# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""DPDP Auto-Purge Scheduler — Phase 6D.

Weekly scheduler that reads Data Retention Rule and processes records
that have aged past their retention window.

CRITICAL SAFETY DESIGN
======================
- Hard cap of HR Settings.dpdp_purge_max_per_run records per execution
  (default 50). Exceeding this just logs a warning and processes the
  first 50 — the rest are deferred to next run.
- 'Delete' action is intentionally NEVER used by the seeded rules.
  Operators must MANUALLY change action_on_expiry to 'Delete' after
  validating the 'Anonymize' behaviour for at least one cycle.
- 'Anonymize' replaces field values with the sentinel string
  '[Anonymized]' for Data-type fields, NULL for everything else.
- 'Archive' dumps the record to /private/files/dpdp_archive/<doctype>/
  <name>.json then deletes the row.
- Every action is logged in Data Access Log so the audit trail survives
  even after the source record is gone.
- Empty / missing anchor_field defaults to 'creation' (always exists).
"""

import json
import os

import frappe
from frappe.utils import add_days, get_files_path, getdate, today


# Fields that are SAFE to anonymise — never touched unless explicitly
# named in a Data Retention Rule with Field-Level scope. For Record-Level
# 'Anonymize' actions, we use this conservative list per doctype.
ANONYMIZE_DEFAULT_FIELDS = {
	"Employee": [
		"personal_email",
		"emergency_phone_number",
		"current_address",
		"permanent_address",
		"bio",
		"pan_number",
		"bank_ac_no",
		"ifsc_code",
	],
	"Salary Slip": [],  # archive-only — no field-level anonymise
	"Form 16": [],
	"Data Access Log": [],  # delete-only safe
	"Employee Tax Exemption Proof Submission": [],
	"POSH Complaint": ["incident_description", "evidence"],
}


def _hr_setting(field, default=None):
	"""Safe HR Settings read — returns default if field doesn't exist."""
	try:
		meta = frappe.get_meta("HR Settings")
		if not meta.get_field(field):
			return default
		val = frappe.db.get_single_value("HR Settings", field)
		return default if val in (None, "") else val
	except Exception:
		return default


def _max_per_run():
	val = _hr_setting("dpdp_purge_max_per_run", 50)
	try:
		return max(1, int(val))
	except Exception:
		return 50


def run_data_retention_purge():
	"""Weekly scheduler entrypoint."""
	rules = frappe.get_all(
		"Data Retention Rule",
		filters={"is_active": 1},
		fields=[
			"name",
			"doctype_name",
			"field_or_record",
			"field_name",
			"retention_period_years",
			"anchor_field",
			"action_on_expiry",
			"applicable_when_condition",
		],
	)
	if not rules:
		return

	cap = _max_per_run()
	processed_total = 0

	for rule in rules:
		try:
			n = _apply_rule(rule, remaining_cap=max(0, cap - processed_total))
			processed_total += n
			if processed_total >= cap:
				frappe.log_error(
					title="DPDP purge: cap reached",
					message=(
						f"Reached HR Settings.dpdp_purge_max_per_run ({cap}) — "
						"remaining rules deferred to next run."
					),
				)
				break
		except Exception:
			frappe.log_error(
				title=f"DPDP purge rule failed: {rule.name}",
				message=frappe.get_traceback(),
			)


def _apply_rule(rule, remaining_cap):
	if remaining_cap <= 0:
		return 0
	if not rule.doctype_name:
		return 0
	if not frappe.db.table_exists(rule.doctype_name):
		return 0

	# Compute cutoff
	years = int(rule.retention_period_years or 0)
	if years <= 0:
		return 0
	cutoff = add_days(today(), -years * 365)
	anchor = rule.anchor_field or "creation"

	# Defensively check the anchor field exists on the doctype.
	try:
		meta = frappe.get_meta(rule.doctype_name)
		if not (
			meta.get_field(anchor)
			or anchor in ("creation", "modified", "owner", "name")
		):
			frappe.log_error(
				title=f"DPDP purge: missing anchor field {anchor} on {rule.doctype_name}",
				message=f"Rule {rule.name} skipped.",
			)
			return 0
	except Exception:
		return 0

	# Build query — strictly limited.
	where = f"`{anchor}` IS NOT NULL AND `{anchor}` < %s"
	params = [cutoff]
	if rule.applicable_when_condition:
		# Caller-validated to not contain ';'
		where += f" AND ({rule.applicable_when_condition})"

	limit = min(remaining_cap, _max_per_run())

	try:
		rows = frappe.db.sql(
			f"""
			SELECT name FROM `tab{rule.doctype_name}`
			WHERE {where}
			LIMIT {limit}
			""",
			tuple(params),
			as_dict=True,
		)
	except Exception:
		frappe.log_error(
			title=f"DPDP purge: query failed on {rule.doctype_name}",
			message=frappe.get_traceback(),
		)
		return 0

	if not rows:
		# Stamp last_purged_on even when nothing matched — proves the rule ran.
		frappe.db.set_value(
			"Data Retention Rule", rule.name, "last_purged_on", today(), update_modified=False
		)
		return 0

	processed = 0
	action = rule.action_on_expiry or "Anonymize"

	for r in rows:
		try:
			ok = _process_record(rule, r.name, action)
			if ok:
				processed += 1
		except Exception:
			frappe.log_error(
				title=f"DPDP purge: failed on {rule.doctype_name}/{r.name}",
				message=frappe.get_traceback(),
			)
		if processed >= limit:
			break

	frappe.db.set_value(
		"Data Retention Rule", rule.name, "last_purged_on", today(), update_modified=False
	)
	return processed


def _process_record(rule, name, action):
	doctype = rule.doctype_name

	# Find subject_employee if possible.
	subject_emp = None
	try:
		meta = frappe.get_meta(doctype)
		if meta.get_field("employee"):
			subject_emp = frappe.db.get_value(doctype, name, "employee")
		elif doctype == "Employee":
			subject_emp = name
	except Exception:
		pass

	from indian_hrms_compliance.overrides.dpdp_access_logger import log_field_access

	if rule.field_or_record == "Field-Level":
		fn = rule.field_name
		if not fn:
			return False
		# Anonymise just the named field.
		try:
			frappe.db.set_value(doctype, name, fn, "[Anonymized]", update_modified=False)
		except Exception:
			# Field might be non-text — fall back to None.
			try:
				frappe.db.set_value(doctype, name, fn, None, update_modified=False)
			except Exception:
				return False
		log_field_access(
			subject_doctype=doctype,
			subject_record=name,
			subject_employee=subject_emp or name,
			field_accessed=fn,
			access_type="Read",
			request_context=f"DPDP Retention Purge ({action}): {rule.name}",
		)
		return True

	# Record-Level
	if action == "Anonymize":
		fields = ANONYMIZE_DEFAULT_FIELDS.get(doctype, [])
		if not fields:
			# Nothing safe to do — skip rather than blast random fields.
			return False
		try:
			meta = frappe.get_meta(doctype)
			fields_present = {f.fieldname for f in meta.fields}
		except Exception:
			fields_present = set()
		count = 0
		for fn in fields:
			if fn not in fields_present:
				continue
			try:
				frappe.db.set_value(doctype, name, fn, "[Anonymized]", update_modified=False)
				count += 1
			except Exception:
				pass
		if count > 0:
			log_field_access(
				subject_doctype=doctype,
				subject_record=name,
				subject_employee=subject_emp or name,
				field_accessed="(record anonymized)",
				access_type="Read",
				request_context=f"DPDP Retention Purge (Anonymize): {rule.name}",
			)
			return True
		return False

	if action == "Archive":
		try:
			doc = frappe.get_doc(doctype, name)
			archive_dir = os.path.join(
				get_files_path(is_private=True), "dpdp_archive", doctype.replace(" ", "_")
			)
			os.makedirs(archive_dir, exist_ok=True)
			payload = doc.as_dict()
			with open(os.path.join(archive_dir, f"{name}.json"), "w") as f:
				json.dump(payload, f, default=str, indent=2)
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
			log_field_access(
				subject_doctype=doctype,
				subject_record=name,
				subject_employee=subject_emp or name,
				field_accessed="(record archived+deleted)",
				access_type="Read",
				request_context=f"DPDP Retention Purge (Archive): {rule.name}",
			)
			return True
		except Exception:
			frappe.log_error(
				title=f"DPDP archive failed: {doctype}/{name}",
				message=frappe.get_traceback(),
			)
			return False

	if action == "Delete":
		try:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
			log_field_access(
				subject_doctype=doctype,
				subject_record=name,
				subject_employee=subject_emp or name,
				field_accessed="(record deleted)",
				access_type="Read",
				request_context=f"DPDP Retention Purge (Delete): {rule.name}",
			)
			return True
		except Exception:
			frappe.log_error(
				title=f"DPDP delete failed: {doctype}/{name}",
				message=frappe.get_traceback(),
			)
			return False

	return False
