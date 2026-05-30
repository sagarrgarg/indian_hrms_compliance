# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Labour Code 2025/2026 headcount-based applicability checker.

Maps a Company's active employee count against the various worker-count
thresholds in the four Codes and reports which obligations apply and
whether the Company already has the corresponding artefact.

Consumed by:
  - JS button on Company form
  - monthly scheduler (monthly_labour_code_compliance_check)
"""

import frappe
from frappe import _


def _hr_setting(field, default=None):
	meta = frappe.get_meta("HR Settings")
	if not meta.get_field(field):
		return default
	val = frappe.db.get_single_value("HR Settings", field)
	return default if val in (None, "") else val


def _worker_count(company):
	"""Active Employee count for a Company."""
	try:
		return frappe.db.count("Employee", {"company": company, "status": "Active"})
	except Exception:
		return 0


def _has_active(doctype, filters):
	"""Return True if at least one matching row exists. Tolerant of
	missing doctypes (returns False)."""
	try:
		if not frappe.db.table_exists(doctype.replace(" ", "")):
			# table_exists takes the actual table name without spaces
			pass
		return frappe.db.exists(doctype, filters) is not None
	except Exception:
		return False


@frappe.whitelist()
def get_labour_code_applicability(company):
	"""Return a dict mapping Labour Code obligations -> applicability /
	current status for the given Company."""
	if not company:
		frappe.throw(_("Company is required."))

	worker_count = _worker_count(company)

	standing_orders_threshold = int(_hr_setting("standing_orders_threshold_workers", 300) or 300)
	works_committee_threshold = int(_hr_setting("works_committee_threshold_workers", 100) or 100)
	grc_threshold = int(_hr_setting("grc_threshold_workers", 20) or 20)
	safety_committee_threshold = int(
		_hr_setting("safety_committee_threshold_workers", 250) or 250
	)
	posh_ic_threshold = int(_hr_setting("posh_ic_threshold_workers", 10) or 10)

	applicability = {
		"company": company,
		"worker_count": worker_count,
		"thresholds": {
			"Standing Orders": standing_orders_threshold,
			"Works Committee": works_committee_threshold,
			"Grievance Redressal Committee": grc_threshold,
			"Safety Committee": safety_committee_threshold,
			"POSH IC": posh_ic_threshold,
		},
		"required": {
			"Standing Orders Required (IR Code §28)": worker_count >= standing_orders_threshold,
			"Works Committee Required (IR Code §3)": worker_count >= works_committee_threshold,
			"Grievance Redressal Committee Required (IR Code §4)": worker_count >= grc_threshold,
			"Safety Committee Required (OSH §96)": worker_count >= safety_committee_threshold,
			"POSH IC Required (POSH Act §4)": worker_count >= posh_ic_threshold,
			"Form 26 Annual Return Required (OSH §6)": True,
		},
		"has": {
			"Has Active Standing Orders": _has_active(
				"Standing Orders", {"company": company, "status": "Active"}
			),
			"Has Active Works Committee": _has_active(
				"Works Committee", {"company": company, "status": "Active"}
			),
			"Has Active GRC": _has_active(
				"Grievance Redressal Committee", {"company": company, "status": "Active"}
			),
			"Has Active POSH IC": _has_active(
				"POSH Internal Committee", {"company": company, "status": "Active"}
			),
			"Has Form 26 (Current FY)": _has_current_fy_form_26(company),
		},
	}

	# Build a flat checklist (used by the JS dialog)
	checklist = []
	# Map required-key -> has-key
	pairs = [
		("Standing Orders Required (IR Code §28)", "Has Active Standing Orders"),
		("Works Committee Required (IR Code §3)", "Has Active Works Committee"),
		("Grievance Redressal Committee Required (IR Code §4)", "Has Active GRC"),
		("POSH IC Required (POSH Act §4)", "Has Active POSH IC"),
		("Form 26 Annual Return Required (OSH §6)", "Has Form 26 (Current FY)"),
		# Safety Committee not yet a dedicated doctype — reported via OSH form
		("Safety Committee Required (OSH §96)", None),
	]
	for req_key, has_key in pairs:
		required = applicability["required"].get(req_key, False)
		present = (
			applicability["has"].get(has_key, False) if has_key else None
		)
		status = "OK"
		if required and has_key is not None and not present:
			status = "Missing"
		elif required and has_key is None:
			status = "Action Required"
		elif not required:
			status = "N/A"
		checklist.append(
			{"requirement": req_key, "required": required, "present": present, "status": status}
		)
	applicability["checklist"] = checklist
	return applicability


def _has_current_fy_form_26(company):
	"""True if an OSH 26 filing exists for the current Fiscal Year on this Co."""
	try:
		from frappe.utils import getdate, today

		fy = frappe.db.sql(
			"""SELECT name FROM `tabFiscal Year`
			   WHERE year_start_date <= %s AND year_end_date >= %s LIMIT 1""",
			(today(), today()),
		)
		if not fy:
			return False
		return bool(
			frappe.db.exists(
				"OSH Annual Return Form 26", {"company": company, "fiscal_year": fy[0][0]}
			)
		)
	except Exception:
		return False


def monthly_labour_code_compliance_check():
	"""Scheduler — for each Company, compute applicability; if required but
	missing, notify HR Manager via PWA + write to error log."""
	if not int(_hr_setting("enable_monthly_labour_code_compliance_check", 1)):
		return

	for company in frappe.get_all("Company", pluck="name"):
		try:
			app = get_labour_code_applicability(company)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Labour Code applicability check failed for {company}",
			)
			continue

		missing = [
			row["requirement"]
			for row in app.get("checklist", [])
			if row["status"] == "Missing"
		]
		if not missing:
			continue

		_notify_hr_managers(company, missing)
		frappe.log_error(
			"\n".join(missing),
			f"Labour Code compliance gaps — {company}",
		)


def _notify_hr_managers(company, missing):
	"""PWA-notify HR Managers about labour-code gaps. Tolerant of missing
	PWA Notification doctype (no-op then)."""
	if not frappe.db.table_exists("tabPWA Notification"):
		return
	hr_managers = frappe.get_all(
		"Has Role",
		filters={"role": "HR Manager", "parenttype": "User"},
		pluck="parent",
	)
	if not hr_managers:
		return
	body = (
		f"Company {company} is missing the following Labour Code obligations:\n• "
		+ "\n• ".join(missing)
	)
	for user in set(hr_managers):
		try:
			frappe.get_doc(
				{
					"doctype": "PWA Notification",
					"to_user": user,
					"from_user": "Administrator",
					"subject": f"[Labour Code] Gaps for {company}",
					"message": body,
					"category": "Compliance",
				}
			).insert(ignore_permissions=True)
		except Exception:
			continue
