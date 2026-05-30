# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""ESI Monthly Contribution Generator — Phase 6B-1.

Produces the monthly ESIC contribution upload CSV for a given
(Company × Wage Month) from submitted Salary Slips.

ESIC portal accepts an Excel template; for our purposes we generate a
clean CSV that maps 1:1 to those columns:

  IP Number | IP Name | No of Days | Total Monthly Wages
  | Reason Code for Zero Workings | Last Working Day

Rates (verified 2026):
  Employee = 0.75% of gross wages
  Employer = 3.25% of gross wages
  Wage ceiling = ₹21,000/mo (₹25,000 for persons with disability)
  Employee share WAIVED if average daily wage ≤ ₹176 (employer pays full)

Critical continuation rule (Reg 26):
  If an employee was contributing in the *prior* month of the current
  *contribution period* (Apr–Sep or Oct–Mar) AND now crosses the ₹21k
  ceiling, they MUST continue contributing until the period ends. We
  implement this by checking prior ESI Monthly Contribution docs for
  the same period for the employee.

Whitelisted entry point: ``generate_esi_monthly(esi_monthly_name)``.
Daily scheduler ``send_esi_due_reminders`` mirrors the PF reminder
pattern.
"""

import csv
import io
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


HR_SETTINGS_DEFAULTS = {
	"esi_wage_ceiling": 21000,
	"esi_wage_ceiling_disabled": 25000,
	"esi_employee_rate_pct": 0.75,
	"esi_employer_rate_pct": 3.25,
	"esi_employee_daily_wage_waiver": 176,
	"esi_filing_window_days": 15,
}


def _hr_setting(field, default=None):
	"""Safe HR Settings read — mirrors the validator pattern."""
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
# Period helpers — Apr-Sep / Oct-Mar
# ---------------------------------------------------------------------------


def _esi_contribution_period(wage_month):
	"""Return (period_label, period_start, period_end) for the given
	wage month under ESI Regulations. Apr-Sep or Oct-Mar."""
	wm = getdate(wage_month)
	if wm.month >= 4 and wm.month <= 9:
		# Apr-Sep of same year
		return ("Apr-Sep", date(wm.year, 4, 1), date(wm.year, 9, 30))
	# Oct-Mar — straddles year boundary
	if wm.month >= 10:
		return ("Oct-Mar", date(wm.year, 10, 1), date(wm.year + 1, 3, 31))
	# Jan-Mar — Oct-Mar period started prior year
	return ("Oct-Mar", date(wm.year - 1, 10, 1), date(wm.year, 3, 31))


def _employee_contributing_prior_in_period(employee, company, wage_month):
	"""True if this employee has a contribution row in *any* ESI Monthly
	Contribution doc for the same company × same period × an earlier
	wage month in that period. Implements ESI continuation rule."""
	_, period_start, _ = _esi_contribution_period(wage_month)
	this_month_start = get_first_day(wage_month)
	if this_month_start <= period_start:
		return False  # First month of period — nothing to continue

	prior = frappe.db.sql(
		"""
		SELECT 1
		FROM `tabESI Monthly Contribution` p
		JOIN `tabESI Monthly Row` r ON r.parent = p.name
		WHERE p.company = %s
		  AND p.wage_month >= %s
		  AND p.wage_month < %s
		  AND p.filing_status != 'Cancelled'
		  AND r.employee = %s
		  AND (r.employee_contribution > 0 OR r.employer_contribution > 0)
		LIMIT 1
		""",
		(company, period_start, this_month_start, employee),
	)
	return bool(prior)


# ---------------------------------------------------------------------------
# Salary slip loaders
# ---------------------------------------------------------------------------


def _get_eligible_salary_slips(company, wage_month):
	wm = getdate(wage_month)
	month_start = get_first_day(wm)
	month_end = get_last_day(wm)
	return frappe.get_all(
		"Salary Slip",
		filters={
			"company": company,
			"docstatus": 1,
			"start_date": (">=", month_start),
			"start_date": ("<=", month_end),
		},
		fields=["name", "employee", "employee_name"],
		order_by="employee",
	)


def _load_slip(slip_name):
	return frappe.get_doc("Salary Slip", slip_name)


# ---------------------------------------------------------------------------
# Per-row computation
# ---------------------------------------------------------------------------


def _slip_gross_wages(slip):
	"""For ESI: gross wages = sum of all earnings rows excluding employer
	share of EPF / EPS / EDLI (which are not counted as wages under ESI
	Sec 2(22)). On a typical slip those don't appear under earnings, so
	we just sum earnings."""
	return sum(flt(r.amount) for r in (slip.earnings or []))


def _slip_no_of_days(slip):
	"""ESI 'No of Days' = paid days in the month."""
	return int(flt(slip.payment_days))


def _compute_esi_row(slip, mapping, settings, prior_contributing):
	"""Build an ESI row dict, or None if the employee is not subject to
	ESI this month (above ceiling, no prior contribution in period)."""
	employee = slip.employee
	gross = _slip_gross_wages(slip)
	days = _slip_no_of_days(slip)

	# Pull employee details for IP number + disability flag.
	emp = frappe.db.get_value(
		"Employee",
		employee,
		["esic_ip_number", "status", "relieving_date"],
		as_dict=True,
	) or {}
	ip_number = emp.get("esic_ip_number") or ""

	# Determine the applicable ceiling. We treat
	# Employee.differently_abled (if exists) as the disability flag;
	# otherwise default ceiling.
	ceiling = flt(settings["esi_wage_ceiling"])
	meta = frappe.get_meta("Employee")
	if meta.get_field("differently_abled"):
		is_disabled = frappe.db.get_value("Employee", employee, "differently_abled")
		if is_disabled:
			ceiling = flt(settings["esi_wage_ceiling_disabled"])

	above_ceiling = gross > ceiling
	if above_ceiling and not prior_contributing:
		# Not subject to ESI this month and not under continuation rule.
		return None

	# Check whether the slip carries explicit ESI deductions (proves ESI
	# applies). If neither the mapping nor a substring match finds an ESI
	# component AND the employee is above ceiling without continuation,
	# we already returned None above. Here we proceed to compute.
	emp_rate = flt(settings["esi_employee_rate_pct"]) / 100.0
	er_rate = flt(settings["esi_employer_rate_pct"]) / 100.0

	# Apply daily-wage waiver for employee share.
	daily_wage_threshold = flt(settings["esi_employee_daily_wage_waiver"])
	avg_daily_wage = (gross / days) if days else gross
	employee_share = 0 if avg_daily_wage <= daily_wage_threshold else gross * emp_rate
	employer_share = gross * er_rate

	# ESIC rounds to nearest rupee in challan generation; mirror that here.
	employee_share = round(employee_share)
	employer_share = round(employer_share)

	# Detect exit during the wage month — set last_working_day for the row.
	last_working_day = None
	wm_start = get_first_day(slip.start_date)
	wm_end = get_last_day(slip.start_date)
	if emp.get("relieving_date"):
		rd = getdate(emp.get("relieving_date"))
		if wm_start <= rd <= wm_end:
			last_working_day = rd

	# Reason code — only when no_of_days = 0.
	reason_code = ""
	if days == 0:
		# Heuristic: pick a reasonable default based on Employee status.
		status = (emp.get("status") or "").lower()
		if status == "left":
			reason_code = "7 - Out of Employment"
		elif status == "suspended":
			reason_code = "5 - Disciplinary Action"
		else:
			reason_code = "1 - On Leave"

	return {
		"employee": employee,
		"employee_name": slip.employee_name,
		"ip_number": ip_number,
		"salary_slip": slip.name,
		"no_of_days": days,
		"total_wages": gross,
		"employee_contribution": employee_share,
		"employer_contribution": employer_share,
		"reason_code_for_zero": reason_code,
		"last_working_day": last_working_day,
	}


# ---------------------------------------------------------------------------
# CSV builder
# ---------------------------------------------------------------------------


ESIC_CSV_HEADERS = [
	"IP Number",
	"IP Name",
	"No of Days",
	"Total Monthly Wages",
	"Reason Code for Zero Workings",
	"Last Working Day",
]


def _build_esi_csv(rows):
	"""Build the ESIC CSV (UTF-8, with header row).

	ESIC portal accepts an Excel template that has these 6 columns; the
	CSV form is a pragmatic stand-in that HR can upload directly OR open
	in Excel + save-as-xlsx."""
	buf = io.StringIO()
	writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
	writer.writerow(ESIC_CSV_HEADERS)
	for r in rows:
		writer.writerow(
			[
				(r.get("ip_number") or "").strip(),
				(r.get("employee_name") or "").strip(),
				int(r.get("no_of_days") or 0),
				int(round(flt(r.get("total_wages")))),
				(r.get("reason_code_for_zero") or "").strip(),
				(r.get("last_working_day").strftime("%d-%m-%Y") if r.get("last_working_day") else ""),
			]
		)
	return buf.getvalue()


def _attach_csv_file(doc, csv_content):
	filename = f"{doc.name}.csv"
	if doc.contribution_file:
		try:
			existing_file = frappe.db.get_value("File", {"file_url": doc.contribution_file}, "name")
			if existing_file:
				frappe.delete_doc("File", existing_file, ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"Old ESI CSV cleanup failed for {doc.name}",
				message=frappe.get_traceback(),
			)
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": filename,
			"content": csv_content,
			"is_private": 1,
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"attached_to_field": "contribution_file",
		}
	).insert(ignore_permissions=True)
	doc.db_set("contribution_file", file_doc.file_url)
	return file_doc.file_url


# ---------------------------------------------------------------------------
# Whitelisted entry point
# ---------------------------------------------------------------------------


@frappe.whitelist()
def generate_esi_monthly(esi_monthly_name):
	"""Generate the ESI monthly contribution CSV + populate rows + totals."""
	doc = frappe.get_doc("ESI Monthly Contribution", esi_monthly_name)
	if doc.filing_status == "Filed":
		frappe.throw(
			_("ESI Monthly Contribution {0} is already Filed — cancel it first to regenerate.").format(
				doc.name
			)
		)
	if doc.filing_status == "Cancelled":
		frappe.throw(_("ESI Monthly Contribution {0} is Cancelled.").format(doc.name))

	mapping = get_mapping_for_company(doc.company)
	settings = {k: _hr_setting(k) for k in HR_SETTINGS_DEFAULTS.keys()}

	# Reset rows.
	doc.set("rows", [])

	slips = _get_eligible_salary_slips(doc.company, doc.wage_month)
	exceptions = []
	rows = []
	excluded_count = 0
	processed_employees = set()

	for slip_meta in slips:
		if slip_meta.employee in processed_employees:
			continue
		processed_employees.add(slip_meta.employee)

		slip = _load_slip(slip_meta.name)
		gross = _slip_gross_wages(slip)
		ceiling = flt(settings["esi_wage_ceiling"])

		prior_contributing = _employee_contributing_prior_in_period(
			slip.employee, doc.company, doc.wage_month
		)
		row = _compute_esi_row(slip, mapping, settings, prior_contributing)
		if not row:
			excluded_count += 1
			# Note exclusions of wage-cap-excluded employees in exceptions
			# only when there's no IP number either (purely informational).
			continue

		if not row["ip_number"]:
			exceptions.append(
				f"- {slip.employee} ({slip.employee_name}): no ESIC IP number on Employee master — "
				f"row generated but the upload will be rejected by the portal."
			)

		rows.append(row)

	# Sort by IP number for stable output.
	rows.sort(key=lambda r: (r["ip_number"] or "", r["employee"]))

	for r in rows:
		doc.append("rows", r)

	# Totals.
	doc.total_ips = len(rows)
	doc.total_wages = sum(flt(r["total_wages"]) for r in rows)
	doc.total_employee_contribution = sum(flt(r["employee_contribution"]) for r in rows)
	doc.total_employer_contribution = sum(flt(r["employer_contribution"]) for r in rows)
	doc.total_contribution = doc.total_employee_contribution + doc.total_employer_contribution
	doc.members_excluded_count = excluded_count
	doc.filing_status = "Generated"
	doc.generated_on = now()

	if not rows:
		exceptions.append(
			"- No employees subject to ESI for this Company × Wage Month "
			"(all above ceiling or no eligible slips)."
		)
	if excluded_count:
		exceptions.append(
			f"- {excluded_count} employee(s) excluded — wages above ESI ceiling and "
			f"not under continuation rule."
		)
	doc.exceptions = "\n".join(exceptions) if exceptions else ""

	doc.save(ignore_permissions=True)

	csv_content = _build_esi_csv(rows)
	_attach_csv_file(doc, csv_content)

	return {
		"name": doc.name,
		"total_ips": doc.total_ips,
		"total_contribution": doc.total_contribution,
		"contribution_file": doc.contribution_file,
		"exceptions_count": len([e for e in exceptions if e]),
	}


@frappe.whitelist()
def mark_esi_filed(esi_monthly_name, challan_number=None):
	doc = frappe.get_doc("ESI Monthly Contribution", esi_monthly_name)
	if doc.filing_status != "Generated":
		frappe.throw(
			_("Only Generated ESI Monthly Contributions can be marked as Filed. Current status: {0}").format(
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
# Daily scheduler — ESI due reminders
# ---------------------------------------------------------------------------


def send_esi_due_reminders():
	"""Daily — alert HR Managers when prior month's ESI is unfiled."""
	window_days = int(_hr_setting("esi_filing_window_days", 15) or 15)
	td = getdate(today())

	this_month_start = get_first_day(td)
	prior_month_start = get_first_day(add_months(this_month_start, -1))
	prior_month_end = get_last_day(prior_month_start)

	if td < add_days(prior_month_end, 1) or td > add_days(prior_month_end, window_days):
		return

	companies = frappe.get_all("Company", fields=["name"])
	for c in companies:
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
		existing = frappe.db.exists(
			"ESI Monthly Contribution",
			{
				"company": c.name,
				"wage_month": prior_month_start,
				"filing_status": ("!=", "Cancelled"),
			},
		)
		if existing:
			status = frappe.db.get_value("ESI Monthly Contribution", existing, "filing_status")
			if status in ("Generated", "Filed"):
				continue
		_notify_esi_due(c.name, prior_month_start, prior_month_end, existing)


def _notify_esi_due(company, wage_month_start, wage_month_end, existing_filing):
	hr_users = frappe.get_all(
		"Has Role",
		filters={"role": "HR Manager", "parenttype": "User"},
		fields=["parent"],
		distinct=True,
	)
	subject = _("ESI Contribution due for {0} — Wage Month {1}").format(
		company, formatdate(wage_month_start, "MMMM yyyy")
	)
	description = _(
		"The ESI Monthly Contribution for {0} (wage month {1} to {2}) is due. "
		"{3} Generate and upload the CSV via the ESI Monthly Contribution doctype."
	).format(
		company,
		formatdate(wage_month_start),
		formatdate(wage_month_end),
		(
			_("Existing draft: {0}.").format(existing_filing)
			if existing_filing
			else _("No filing exists yet.")
		),
	)
	ref_doctype = "ESI Monthly Contribution" if existing_filing else "Company"
	ref_name = existing_filing or company

	for u in hr_users:
		user = u.parent
		if user in ("Administrator", "Guest"):
			continue
		todo_exists = frappe.db.exists(
			"ToDo",
			{
				"allocated_to": user,
				"reference_type": ref_doctype,
				"reference_name": ref_name,
				"description": ("like", f"%ESI due for {company} - {formatdate(wage_month_start, 'MMMM yyyy')}%"),
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
					"reference_type": ref_doctype,
					"reference_name": ref_name,
					"description": f"ESI due for {company} - {formatdate(wage_month_start, 'MMMM yyyy')}: {description}",
					"priority": "High",
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"ESI ToDo creation failed for {user}",
				message=frappe.get_traceback(),
			)
		_pwa_notify(user, subject, description, existing_filing, company)


def _pwa_notify(user, subject, description, existing_filing, company):
	if not frappe.db.exists("DocType", "PWA Notification"):
		return
	try:
		ref_doctype = "ESI Monthly Contribution" if existing_filing else "Company"
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
		frappe.log_error(
			title=f"PWA notification failed for {user}",
			message=frappe.get_traceback(),
		)
