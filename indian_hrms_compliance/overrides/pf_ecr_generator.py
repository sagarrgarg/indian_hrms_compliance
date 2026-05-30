# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""PF ECR Generator — Phase 6B-1.

Produces the monthly EPFO Electronic Challan-cum-Return (ECR) text
file from submitted Salary Slips for a given (Company × Wage Month).

EPFO ECR 2.0 format reference: epfindia.gov.in → For Employers →
Establishments → ECR Format. Pipe-delimited (separator: '#~#'), one
row per UAN, 11 columns:

  UAN | Member Name | Gross Wages | EPF Wages | EPS Wages | EDLI Wages
  | EPF Contribution Remitted | EPS Contribution Remitted
  | EPF EPS Diff Remitted | NCP Days | Refund of Advances

Computation rules (verified for 2026 wage period):
  EPF Wages  = Basic + DA (uncapped at the employer-share level if the
               establishment has opted-in to contribute on actual; we
               cap at HR Settings.pf_wage_ceiling only for EPS/EDLI).
  EPS Wages  = min(EPF Wages, 15000)
  EDLI Wages = min(EPF Wages, 15000)
  EPF Contribution Remitted = round(EPF Wages × 12%) — employee share
  EPS Contribution Remitted = round(EPS Wages × 8.33%) — employer share to A/c 10
  EPF EPS Diff Remitted = EPF Contribution − EPS Contribution
                        = employer A/c 1 share (the "diff" is on the employer side)
  NCP Days = Salary Slip.leave_without_pay + Salary Slip.absent_days

Establishment-level admin charges (A/c 2, A/c 21) are aggregated at the
filing level (not per row in the ECR — they live on the challan side):
  EDLI total = sum of EDLI Wages × 0.50%, min 75 per member if any
  Admin total = max(sum of EPF Wages × 0.50%, 500)

The whitelisted entry point is ``generate_pf_ecr(pf_ecr_filing_name)``;
it (1) clears existing rows, (2) loads eligible Salary Slips, (3)
computes each row, (4) sums totals, (5) writes the .txt file, (6)
attaches it to the parent doc, (7) flips status to Generated.

A daily scheduler ``send_pf_ecr_due_reminders`` runs from hooks.py;
when the wage month closed N days ago (N = HR
Settings.pf_ecr_filing_window_days, default 15) and no filing exists
for that (Company × wage_month), it ToDo's HR Managers + sends a PWA
notification.
"""

import csv
import io
import json
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	add_months,
	flt,
	formatdate,
	get_first_day,
	get_last_day,
	getdate,
	now,
	nowdate,
	today,
)

from indian_hrms_compliance.hr.doctype.statutory_component_mapping.statutory_component_mapping import (
	get_mapping_for_company,
)


# Defaults mirror the verified 2026 PF rates (matches
# overrides/salary_structure_validator.HR_SETTINGS_DEFAULTS).
HR_SETTINGS_DEFAULTS = {
	"pf_wage_ceiling": 15000,
	"pf_employee_rate_pct": 12.0,
	"pf_employer_rate_pct": 12.0,
	"pf_eps_rate_pct": 8.33,
	"pf_edli_rate_pct": 0.50,
	"pf_admin_charges_pct": 0.50,
	"pf_admin_charges_min": 500,
	"pf_edli_per_member_cap": 75,
	"pf_ecr_filing_window_days": 15,
	"pf_ecr_exclude_employees_with_no_uan": 1,
}

# EPFO ECR field separator — pipe wrapped in '#~#' per spec.
ECR_FIELD_SEP = "#~#"
# Line terminator — EPFO accepts both LF and CRLF; we use LF for
# consistency.
ECR_LINE_SEP = "\n"


# ---------------------------------------------------------------------------
# HR Settings safe helper (mirrors validator pattern)
# ---------------------------------------------------------------------------


def _hr_setting(field, default=None):
	"""Safe HR Settings read — returns default if the field doesn't exist
	yet (e.g., before the patches that add the fields have run)."""
	meta = frappe.get_meta("HR Settings")
	if not meta.get_field(field):
		if default is not None:
			return default
		return HR_SETTINGS_DEFAULTS.get(field)
	val = frappe.db.get_single_value("HR Settings", field)
	if val in (None, ""):
		if default is not None:
			return default
		return HR_SETTINGS_DEFAULTS.get(field)
	return val


# ---------------------------------------------------------------------------
# Salary Slip loaders
# ---------------------------------------------------------------------------


def _get_eligible_salary_slips(company, wage_month):
	"""Return submitted Salary Slip names whose start_date falls in
	``wage_month`` (month + year) and are for the given Company."""
	wage_month = getdate(wage_month)
	month_start = get_first_day(wage_month)
	month_end = get_last_day(wage_month)
	return frappe.get_all(
		"Salary Slip",
		filters={
			"company": company,
			"docstatus": 1,
			"start_date": (">=", month_start),
			"start_date": ("<=", month_end),
		},
		fields=["name", "employee", "employee_name", "start_date", "end_date"],
		order_by="employee",
	)


def _load_slip(slip_name):
	return frappe.get_doc("Salary Slip", slip_name)


# ---------------------------------------------------------------------------
# Per-row computation
# ---------------------------------------------------------------------------


def _component_amount(slip, component_name, parentfield):
	"""Return the amount of a given Salary Component on a slip's
	earnings/deductions table. Returns 0 if not present."""
	if not component_name:
		return 0
	for row in slip.get(parentfield) or []:
		if row.salary_component == component_name:
			return flt(row.amount)
	return 0


def _earnings_amount(slip, component_name):
	return _component_amount(slip, component_name, "earnings")


def _deduction_amount(slip, component_name):
	return _component_amount(slip, component_name, "deductions")


def _slip_basic_plus_da(slip, mapping):
	"""Resolve Basic + DA from the slip using the Statutory Component
	Mapping. Falls back to substring matching when mapping is missing."""
	total = 0
	basic_comp = mapping.basic_component if mapping else None
	da_comp = mapping.da_component if mapping else None
	matched = False
	for row in slip.earnings or []:
		if basic_comp and row.salary_component == basic_comp:
			total += flt(row.amount)
			matched = True
			continue
		if da_comp and row.salary_component == da_comp:
			total += flt(row.amount)
			matched = True
			continue
	if matched:
		return total
	# Fallback — substring match (only kicks in when mapping has neither
	# basic nor DA set; required so the generator still produces *some*
	# output on greenfield setups).
	if not (basic_comp or da_comp):
		for row in slip.earnings or []:
			lower = (row.salary_component or "").lower()
			if "basic" in lower or "dearness" in lower or lower == "da":
				total += flt(row.amount)
	return total


def _slip_gross_wages(slip):
	"""Gross wages = sum of all earnings rows on the slip. EPFO defines
	'Gross Wages' broadly as total monthly wages (everything counted as
	salary), independent of the EPF wage base."""
	return sum(flt(r.amount) for r in (slip.earnings or []))


def _slip_ncp_days(slip):
	"""Non-Contributing Period = LOP + absent days. Salary Slip stores
	these as separate fields."""
	return int(flt(slip.leave_without_pay) + flt(slip.absent_days))


def _compute_pf_row(slip, mapping, settings):
	"""Returns a dict ready to be appended to PF ECR Filing.rows, OR
	None if the employee should not be in this ECR (e.g., no PF
	Employee component on their structure → they're not a PF member).

	Side-effect: never raises — pure computation."""
	# Determine PF applicability for this slip. Heuristic: if the slip
	# contains the PF Employee deduction component (per mapping) with a
	# non-zero amount, OR the employer share is present, the employee is
	# a PF member for this month.
	pf_employee_comp = mapping.pf_employee_component if mapping else None
	pf_employer_comp = mapping.pf_employer_component if mapping else None

	pf_emp_amount = _deduction_amount(slip, pf_employee_comp) if pf_employee_comp else 0
	pf_employer_amount = (
		_deduction_amount(slip, pf_employer_comp) if pf_employer_comp else 0
	) or (
		_earnings_amount(slip, pf_employer_comp) if pf_employer_comp else 0
	)

	# Substring fallback when no mapping exists.
	if not pf_emp_amount and not mapping:
		for row in slip.deductions or []:
			lower = (row.salary_component or "").lower()
			if ("provident fund" in lower or lower == "pf" or "epf" in lower) and "loan" not in lower:
				pf_emp_amount = flt(row.amount)
				break

	# If the slip has neither PF employee nor employer component, this
	# employee is not a PF member (e.g., excluded employee earning above
	# ceiling and not opted-in).
	if not (pf_emp_amount or pf_employer_amount):
		return None

	pf_ceiling = flt(settings["pf_wage_ceiling"])
	epf_rate = flt(settings["pf_employee_rate_pct"]) / 100.0

	gross_wages = _slip_gross_wages(slip)
	epf_wages = _slip_basic_plus_da(slip, mapping)

	# If we couldn't compute Basic + DA from the slip but PF was clearly
	# deducted, back-derive EPF wages from the deducted amount.
	if not epf_wages and pf_emp_amount and epf_rate:
		epf_wages = pf_emp_amount / epf_rate

	eps_wages = min(epf_wages, pf_ceiling)
	edli_wages = min(epf_wages, pf_ceiling)

	# EPFO rounds to nearest integer rupee for all per-row contribution
	# figures. round() with ties-to-even is fine — half-rupee ties are
	# vanishingly rare given the rate × ₹ wage product.
	epf_contribution = round(epf_wages * epf_rate)
	eps_contribution = round(eps_wages * flt(settings["pf_eps_rate_pct"]) / 100.0)
	# EPS contribution caps at 1,250 (8.33% × 15,000); the round() above
	# already respects that since eps_wages is capped at 15,000.
	epf_eps_diff = epf_contribution - eps_contribution

	ncp_days = _slip_ncp_days(slip)

	return {
		"employee": slip.employee,
		"employee_name": slip.employee_name,
		"uan": _employee_uan(slip.employee),
		"salary_slip": slip.name,
		"gross_wages": gross_wages,
		"epf_wages": epf_wages,
		"eps_wages": eps_wages,
		"edli_wages": edli_wages,
		"epf_contribution": epf_contribution,
		"eps_contribution": eps_contribution,
		"epf_eps_diff": epf_eps_diff,
		"ncp_days": ncp_days,
		"refund_of_advances": 0,
	}


def _employee_uan(employee):
	"""Look up UAN from Employee.uan_number. Returns '' if unset."""
	if not employee:
		return ""
	return frappe.db.get_value("Employee", employee, "uan_number") or ""


# ---------------------------------------------------------------------------
# ECR text file builder
# ---------------------------------------------------------------------------


def _build_ecr_txt(rows):
	"""Build the pipe-delimited ECR body per EPFO ECR 2.0 spec.

	Each row = 11 fields separated by ECR_FIELD_SEP. Numeric fields are
	formatted as integers (EPFO rejects decimals in ECR 2.0). Member
	Name is truncated to 85 chars (EPFO cap) and sanitised to remove
	the separator character defensively."""
	lines = []
	for r in rows:
		name = (r.get("employee_name") or "").replace(ECR_FIELD_SEP, " ").strip()[:85]
		uan = (r.get("uan") or "").strip()
		fields = [
			uan,
			name,
			str(int(round(flt(r.get("gross_wages"))))),
			str(int(round(flt(r.get("epf_wages"))))),
			str(int(round(flt(r.get("eps_wages"))))),
			str(int(round(flt(r.get("edli_wages"))))),
			str(int(round(flt(r.get("epf_contribution"))))),
			str(int(round(flt(r.get("eps_contribution"))))),
			str(int(round(flt(r.get("epf_eps_diff"))))),
			str(int(r.get("ncp_days") or 0)),
			str(int(round(flt(r.get("refund_of_advances"))))),
		]
		lines.append(ECR_FIELD_SEP.join(fields))
	return ECR_LINE_SEP.join(lines) + ECR_LINE_SEP


def _attach_ecr_file(doc, txt_content):
	"""Save the .txt as a private File attached to ``doc`` and update
	doc.ecr_file with the resulting file URL."""
	filename = f"{doc.name}.txt"
	# Detach any prior attachment for idempotency (re-running Generate).
	if doc.ecr_file:
		try:
			existing_file = frappe.db.get_value("File", {"file_url": doc.ecr_file}, "name")
			if existing_file:
				frappe.delete_doc("File", existing_file, ignore_permissions=True)
		except Exception:
			# Don't fail the whole generate if old file cleanup fails.
			frappe.log_error(
				title=f"Old ECR file cleanup failed for {doc.name}",
				message=frappe.get_traceback(),
			)
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": filename,
			"content": txt_content,
			"is_private": 1,
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"attached_to_field": "ecr_file",
		}
	).insert(ignore_permissions=True)
	doc.db_set("ecr_file", file_doc.file_url)
	return file_doc.file_url


# ---------------------------------------------------------------------------
# Whitelisted entry point
# ---------------------------------------------------------------------------


@frappe.whitelist()
def generate_pf_ecr(pf_ecr_filing_name):
	"""Generate the ECR for a PF ECR Filing draft.

	Idempotent — re-running on an already-Generated doc clears prior
	rows and regenerates from scratch (HR may have submitted a missed
	Salary Slip mid-cycle)."""
	doc = frappe.get_doc("PF ECR Filing", pf_ecr_filing_name)
	if doc.filing_status == "Filed":
		frappe.throw(
			_(
				"PF ECR Filing {0} is already Filed — cannot regenerate. Cancel it first if you need to refile."
			).format(doc.name)
		)
	if doc.filing_status == "Cancelled":
		frappe.throw(_("PF ECR Filing {0} is Cancelled.").format(doc.name))

	mapping = get_mapping_for_company(doc.company)
	settings = {k: _hr_setting(k) for k in HR_SETTINGS_DEFAULTS.keys()}

	# Clear existing rows for idempotency.
	doc.set("rows", [])

	# Load eligible Salary Slips.
	slips = _get_eligible_salary_slips(doc.company, doc.wage_month)
	exceptions = []
	rows = []
	exclude_no_uan = int(settings.get("pf_ecr_exclude_employees_with_no_uan") or 1)
	skipped_no_uan = 0
	skipped_not_pf_member = 0
	processed_employees = set()

	for slip_meta in slips:
		# Belt-and-braces: skip duplicate employee in same month.
		if slip_meta.employee in processed_employees:
			continue
		processed_employees.add(slip_meta.employee)

		slip = _load_slip(slip_meta.name)
		row = _compute_pf_row(slip, mapping, settings)
		if not row:
			skipped_not_pf_member += 1
			continue

		if not row["uan"]:
			if exclude_no_uan:
				exceptions.append(
					f"- {slip.employee} ({slip.employee_name}): no UAN on Employee master — skipped."
				)
				skipped_no_uan += 1
				continue
			else:
				frappe.throw(
					_(
						"Employee {0} ({1}) has no UAN on the Employee master. Set HR "
						"Settings.pf_ecr_exclude_employees_with_no_uan = 1 to skip such "
						"employees, or capture UAN before generating."
					).format(slip.employee, slip.employee_name)
				)

		rows.append(row)

	# Sort by UAN for stable output.
	rows.sort(key=lambda r: r["uan"])

	# Append rows to the doc.
	for r in rows:
		doc.append("rows", r)

	# Compute totals.
	doc.total_members = len(rows)
	doc.total_gross_wages = sum(flt(r["gross_wages"]) for r in rows)
	doc.total_epf_wages = sum(flt(r["epf_wages"]) for r in rows)
	doc.total_eps_wages = sum(flt(r["eps_wages"]) for r in rows)
	doc.total_epf_contribution = sum(flt(r["epf_contribution"]) for r in rows)
	doc.total_eps_contribution = sum(flt(r["eps_contribution"]) for r in rows)
	# EDLI — per-member contribution = EDLI Wages × 0.50%, capped at 75 per
	# member (since EDLI wage cap × rate = 15000 × 0.005 = 75). The cap is
	# already implicit because eps_wages is capped at 15000.
	edli_rate = flt(settings["pf_edli_rate_pct"]) / 100.0
	edli_cap_per_member = flt(settings.get("pf_edli_per_member_cap") or 75)
	doc.total_edli_contribution = sum(
		min(round(flt(r["edli_wages"]) * edli_rate), edli_cap_per_member) for r in rows
	)
	# Admin charges — 0.50% of total EPF Wages, with a per-establishment
	# floor of ₹500.
	admin_rate = flt(settings["pf_admin_charges_pct"]) / 100.0
	admin_min = flt(settings["pf_admin_charges_min"])
	doc.total_admin_charges = max(round(flt(doc.total_epf_wages) * admin_rate), admin_min) if rows else 0
	doc.total_remittance = (
		flt(doc.total_epf_contribution)
		+ flt(doc.total_eps_contribution)
		+ flt(doc.total_edli_contribution)
		+ flt(doc.total_admin_charges)
	)
	doc.challan_amount = doc.total_remittance
	doc.filing_status = "Generated"
	doc.generated_on = now()

	# Build exception list message.
	if not rows:
		exceptions.append(
			"- No eligible Salary Slips found for this Company × Wage Month. "
			"Ensure slips are submitted before regenerating."
		)
	if skipped_not_pf_member:
		exceptions.append(
			f"- {skipped_not_pf_member} submitted slip(s) had no PF component — treated as non-PF employees."
		)
	if skipped_no_uan:
		exceptions.append(
			f"- {skipped_no_uan} employee(s) skipped due to missing UAN."
		)
	doc.exceptions = "\n".join(exceptions) if exceptions else ""

	# Save before attaching file (so attachment can reference doc.name).
	doc.save(ignore_permissions=True)

	# Build and attach the ECR text file.
	txt_content = _build_ecr_txt(rows)
	_attach_ecr_file(doc, txt_content)

	return {
		"name": doc.name,
		"total_members": doc.total_members,
		"total_remittance": doc.total_remittance,
		"ecr_file": doc.ecr_file,
		"exceptions_count": len([e for e in exceptions if e]),
	}


@frappe.whitelist()
def mark_pf_ecr_filed(pf_ecr_filing_name, challan_number=None):
	"""Flip filing_status to Filed and capture challan_number + filed_on."""
	doc = frappe.get_doc("PF ECR Filing", pf_ecr_filing_name)
	if doc.filing_status != "Generated":
		frappe.throw(
			_("Only Generated PF ECR Filings can be marked as Filed. Current status: {0}").format(
				doc.filing_status
			)
		)
	doc.filing_status = "Filed"
	doc.filed_on = nowdate()
	if challan_number:
		doc.challan_number = challan_number
	doc.save(ignore_permissions=True)
	return doc.name


# ---------------------------------------------------------------------------
# Daily scheduler — PF ECR due reminders
# ---------------------------------------------------------------------------


def send_pf_ecr_due_reminders():
	"""Daily scheduler — alert HR Managers when the prior wage month's
	ECR is due and no filing exists.

	Window: today ∈ [wage_month_end + 1, wage_month_end + pf_ecr_filing_window_days].
	"""
	window_days = int(_hr_setting("pf_ecr_filing_window_days", 15) or 15)
	td = getdate(today())

	# Determine the "prior wage month" — generally the month before today.
	# Example: today = 2026-06-05 → prior wage month start = 2026-05-01,
	# end = 2026-05-31; window = 06-01 .. 06-15.
	this_month_start = get_first_day(td)
	prior_month_start = get_first_day(add_months(this_month_start, -1))
	prior_month_end = get_last_day(prior_month_start)

	if td < add_days(prior_month_end, 1) or td > add_days(prior_month_end, window_days):
		return  # Not in the reminder window

	companies = frappe.get_all("Company", fields=["name"])
	for c in companies:
		# Only remind if this company has any PF-applicable Salary Slip in
		# the prior month (i.e., there's something to file).
		has_slips = frappe.db.exists(
			"Salary Slip",
			{
				"company": c.name,
				"docstatus": 1,
				"start_date": ("between", [prior_month_start, prior_month_end]),
			},
		)
		if not has_slips:
			continue
		# Has a filing already been raised for this period?
		existing = frappe.db.exists(
			"PF ECR Filing",
			{
				"company": c.name,
				"wage_month": prior_month_start,
				"filing_status": ("!=", "Cancelled"),
			},
		)
		if existing:
			# Even if exists, remind if still Draft within the window.
			status = frappe.db.get_value("PF ECR Filing", existing, "filing_status")
			if status in ("Generated", "Filed"):
				continue

		_notify_pf_ecr_due(c.name, prior_month_start, prior_month_end, existing)


def _notify_pf_ecr_due(company, wage_month_start, wage_month_end, existing_filing):
	"""Create ToDos for HR Manager users + PWA notify."""
	hr_users = frappe.get_all(
		"Has Role",
		filters={"role": "HR Manager", "parenttype": "User"},
		fields=["parent"],
		distinct=True,
	)
	subject = _("PF ECR due for {0} — Wage Month {1}").format(
		company, formatdate(wage_month_start, "MMMM yyyy")
	)
	description = _(
		"The Provident Fund ECR for {0} (wage month {1} to {2}) is due. "
		"{3} Generate and file it via the PF ECR Filing doctype."
	).format(
		company,
		formatdate(wage_month_start),
		formatdate(wage_month_end),
		(_("Existing draft: {0}.").format(existing_filing) if existing_filing else _("No filing exists yet.")),
	)
	for u in hr_users:
		user = u.parent
		if user in ("Administrator", "Guest"):
			continue
		# Idempotency: skip if a ToDo for this user / company / month
		# already exists and is Open.
		todo_exists = frappe.db.exists(
			"ToDo",
			{
				"allocated_to": user,
				"reference_type": "PF ECR Filing" if existing_filing else "Company",
				"reference_name": existing_filing or company,
				"description": ("like", f"%PF ECR due for {company} - {formatdate(wage_month_start, 'MMMM yyyy')}%"),
				"status": "Open",
			},
		)
		if todo_exists:
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "ToDo",
					"allocated_to": user,
					"reference_type": "PF ECR Filing" if existing_filing else "Company",
					"reference_name": existing_filing or company,
					"description": f"PF ECR due for {company} - {formatdate(wage_month_start, 'MMMM yyyy')}: {description}",
					"priority": "High",
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"PF ECR ToDo creation failed for {user}",
				message=frappe.get_traceback(),
			)
		_pwa_notify(user, subject, description, existing_filing, company)


def _pwa_notify(user, subject, description, existing_filing, company):
	"""Best-effort PWA Notification insert. PWA Notification doctype
	exists in this app; silently no-op if its schema changes."""
	if not frappe.db.exists("DocType", "PWA Notification"):
		return
	try:
		ref_doctype = "PF ECR Filing" if existing_filing else "Company"
		ref_name = existing_filing or company
		frappe.get_doc(
			{
				"doctype": "PWA Notification",
				"to_user": user,
				"from_user": "Administrator",
				"message": f"{subject}: {description}",
				"reference_document_type": ref_doctype,
				"reference_document_name": ref_name,
				"category": "Compliance",
			}
		).insert(ignore_permissions=True)
	except Exception:
		# PWA Notification schema may differ across forks — log and move on.
		frappe.log_error(
			title=f"PWA notification failed for {user}",
			message=frappe.get_traceback(),
		)
