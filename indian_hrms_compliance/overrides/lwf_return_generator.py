# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Labour Welfare Fund Return Generator — Phase 6B-2.

Produces a per-employee LWF CSV for (Company × State × Period) by
pulling LWF Employee + LWF Employer salary components from submitted
Salary Slips in the period.

State-driven filing frequency:
  - Monthly: MH (LWF dropped 2015, but spec retained) — most states are not monthly
  - Half-yearly: MH (₹6 emp + ₹18 employer), GJ (₹6 + ₹12), WB (₹3 + ₹15)
  - Annual: KA, TN, AP, TG, KL, HR, PB, MP

Generator does NOT compute expected LWF amounts (per-state notification
schedule is too varied — small flat figures), only sums what the slip
deductions/contributions say.
"""

import csv
import io

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
from indian_hrms_compliance.overrides._state_resolver import resolve_employee_state


HR_SETTINGS_DEFAULTS = {
	"lwf_filing_window_days": 15,
}


def _hr_setting(field, default=None):
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
# Salary Slip aggregation
# ---------------------------------------------------------------------------


def _slips_in_period(company, period_start, period_end):
	return frappe.get_all(
		"Salary Slip",
		filters={
			"company": company,
			"docstatus": 1,
			"start_date": (">=", period_start),
			"start_date": ("<=", period_end),
		},
		fields=["name", "employee", "employee_name", "start_date", "end_date"],
		order_by="employee, start_date",
	)


def _component_amount(slip, component_name, parentfield):
	if not component_name:
		return 0
	for r in slip.get(parentfield) or []:
		if r.salary_component == component_name:
			return flt(r.amount)
	return 0


def _slip_employee_lwf(slip, mapping):
	comp = mapping.lwf_employee_component if mapping else None
	if comp:
		return _component_amount(slip, comp, "deductions")
	# Substring fallback — employee LWF appears in deductions.
	for r in slip.get("deductions") or []:
		lower = (r.salary_component or "").lower()
		if "lwf" in lower and "employer" not in lower:
			return flt(r.amount)
		if "labour welfare" in lower and "employer" not in lower:
			return flt(r.amount)
	return 0


def _slip_employer_lwf(slip, mapping):
	comp = mapping.lwf_employer_component if mapping else None
	if comp:
		# Employer LWF can appear in either earnings (added-then-recovered)
		# or deductions depending on accounting style; check both.
		return _component_amount(slip, comp, "deductions") or _component_amount(
			slip, comp, "earnings"
		)
	for r in (slip.get("deductions") or []) + (slip.get("earnings") or []):
		lower = (r.salary_component or "").lower()
		if "employer lwf" in lower or "lwf employer" in lower or "employer labour welfare" in lower:
			return flt(r.amount)
	return 0


def _slip_gross_earnings(slip):
	return sum(flt(r.amount) for r in (slip.get("earnings") or []))


# ---------------------------------------------------------------------------
# CSV builder
# ---------------------------------------------------------------------------


LWF_CSV_HEADERS = [
	"Employee Code",
	"Employee Name",
	"Gross Wages",
	"Employee LWF",
	"Employer LWF",
	"Total LWF",
	"Salary Slip",
]


def _build_lwf_csv(rows):
	buf = io.StringIO()
	writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
	writer.writerow(LWF_CSV_HEADERS)
	for r in rows:
		writer.writerow(
			[
				(r.get("employee") or "").strip(),
				(r.get("employee_name") or "").strip(),
				int(round(flt(r.get("gross_wages")))),
				int(round(flt(r.get("employee_lwf")))),
				int(round(flt(r.get("employer_lwf")))),
				int(round(flt(r.get("employee_lwf")) + flt(r.get("employer_lwf")))),
				(r.get("salary_slip") or "").strip(),
			]
		)
	return buf.getvalue()


def _attach_csv(doc, csv_content, fieldname="lwf_csv"):
	filename = f"{doc.name}.csv"
	existing_url = doc.get(fieldname)
	if existing_url:
		try:
			existing = frappe.db.get_value("File", {"file_url": existing_url}, "name")
			if existing:
				frappe.delete_doc("File", existing, ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"Old LWF CSV cleanup failed for {doc.name}",
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
			"attached_to_field": fieldname,
		}
	).insert(ignore_permissions=True)
	doc.db_set(fieldname, file_doc.file_url)
	return file_doc.file_url


# ---------------------------------------------------------------------------
# Whitelisted entry point
# ---------------------------------------------------------------------------


@frappe.whitelist()
def generate_lwf_return(lwf_return_name):
	"""Build per-employee LWF rows + CSV. Idempotent."""
	doc = frappe.get_doc("LWF Return", lwf_return_name)
	if doc.filing_status == "Filed":
		frappe.throw(
			_("LWF Return {0} is already Filed — cancel it first.").format(doc.name)
		)
	if doc.filing_status == "Cancelled":
		frappe.throw(_("LWF Return {0} is Cancelled.").format(doc.name))

	state_doc = frappe.get_doc("Indian State", doc.state)
	if not state_doc.lwf_applicable:
		frappe.throw(
			_("LWF is not applicable in {0} per the Indian State master. Aborting.").format(
				doc.state
			)
		)

	mapping = get_mapping_for_company(doc.company)

	# Reset rows.
	doc.set("rows", [])

	slips = _slips_in_period(doc.company, doc.period_start, doc.period_end)

	employee_aggregate = {}
	exceptions = []
	skipped_other_state = 0
	skipped_no_state = 0

	for slip_meta in slips:
		emp_state = resolve_employee_state(slip_meta.employee)
		if not emp_state:
			exceptions.append(
				f"- {slip_meta.employee} ({slip_meta.employee_name}): no resolvable state."
			)
			skipped_no_state += 1
			continue
		if emp_state != doc.state:
			skipped_other_state += 1
			continue

		slip = frappe.get_doc("Salary Slip", slip_meta.name)
		emp_lwf = _slip_employee_lwf(slip, mapping)
		er_lwf = _slip_employer_lwf(slip, mapping)
		gross = _slip_gross_earnings(slip)

		bucket = employee_aggregate.setdefault(
			slip.employee,
			{
				"employee": slip.employee,
				"employee_name": slip.employee_name,
				"gross_wages": 0,
				"employee_lwf": 0,
				"employer_lwf": 0,
				"salary_slip": slip.name,
			},
		)
		bucket["gross_wages"] += gross
		bucket["employee_lwf"] += emp_lwf
		bucket["employer_lwf"] += er_lwf
		bucket["salary_slip"] = slip.name

	rows = sorted(employee_aggregate.values(), key=lambda r: r["employee"])
	for r in rows:
		doc.append("rows", r)

	doc.total_employees = len(rows)
	doc.total_employee_contribution = sum(flt(r["employee_lwf"]) for r in rows)
	doc.total_employer_contribution = sum(flt(r["employer_lwf"]) for r in rows)
	doc.total_contribution = doc.total_employee_contribution + doc.total_employer_contribution
	doc.filing_status = "Generated"
	doc.generated_on = now()

	# LWF gut-check — flag rows with zero contribution despite being in a
	# state where LWF applies (the salary structure may not have LWF
	# components mapped).
	zero_contrib = [r for r in rows if not (flt(r["employee_lwf"]) or flt(r["employer_lwf"]))]
	if zero_contrib:
		exceptions.append(
			f"- {len(zero_contrib)} employee(s) had zero LWF deduction in a LWF-applicable state — "
			f"check Statutory Component Mapping (lwf_employee_component / lwf_employer_component)."
		)
	if not rows:
		exceptions.append(
			f"- No employees resolved to state {doc.state} for the given period."
		)
	if skipped_other_state:
		exceptions.append(
			f"- {skipped_other_state} salary slip(s) belonged to other states — not in this return."
		)
	if skipped_no_state:
		exceptions.append(
			f"- {skipped_no_state} salary slip(s) skipped — employee state could not be resolved."
		)
	doc.exceptions = "\n".join(exceptions) if exceptions else ""

	doc.save(ignore_permissions=True)

	csv_content = _build_lwf_csv(rows)
	_attach_csv(doc, csv_content, fieldname="lwf_csv")

	return {
		"name": doc.name,
		"total_employees": doc.total_employees,
		"total_contribution": doc.total_contribution,
		"lwf_csv": doc.lwf_csv,
		"exceptions_count": len([e for e in exceptions if e]),
	}


@frappe.whitelist()
def mark_lwf_return_filed(lwf_return_name):
	doc = frappe.get_doc("LWF Return", lwf_return_name)
	if doc.filing_status != "Generated":
		frappe.throw(
			_("Only Generated LWF Returns can be marked as Filed. Current status: {0}").format(
				doc.filing_status
			)
		)
	doc.filing_status = "Filed"
	doc.filed_on = nowdate()
	doc.save(ignore_permissions=True)
	return doc.name


# ---------------------------------------------------------------------------
# Daily scheduler
# ---------------------------------------------------------------------------


def send_lwf_return_due_reminders():
	"""Daily — alert HR Managers when a state's LWF return for the most
	recent period is unfiled and within the reminder window."""
	window_days = int(_hr_setting("lwf_filing_window_days", 15) or 15)
	td = getdate(today())

	companies = frappe.get_all("Company", fields=["name"])
	states = frappe.get_all(
		"Indian State", filters={"lwf_applicable": 1}, fields=["name", "lwf_filing_frequency"]
	)

	for c in companies:
		for st in states:
			period_start, period_end = _prior_lwf_period(td, st.lwf_filing_frequency)
			if not period_end:
				continue
			if td < add_days(period_end, 1) or td > add_days(period_end, window_days):
				continue
			has_slips = frappe.db.exists(
				"Salary Slip",
				{
					"company": c.name,
					"docstatus": 1,
					"start_date": ("between", [period_start, period_end]),
				},
			)
			if not has_slips:
				continue
			existing = frappe.db.exists(
				"LWF Return",
				{
					"company": c.name,
					"state": st.name,
					"period_start": period_start,
					"period_end": period_end,
					"filing_status": ("!=", "Cancelled"),
				},
			)
			if existing and frappe.db.get_value("LWF Return", existing, "filing_status") == "Filed":
				continue
			_notify_lwf_due(c.name, st.name, period_start, period_end, existing)


def _prior_lwf_period(today_date, frequency):
	"""Return (start, end) of the *prior* LWF filing period."""
	if not frequency:
		return None, None
	if frequency == "Monthly":
		this_start = get_first_day(today_date)
		prior_start = get_first_day(add_months(this_start, -1))
		return prior_start, get_last_day(prior_start)
	if frequency == "Half-yearly":
		m = today_date.month
		y = today_date.year
		if m >= 7 and m <= 12:
			# Current = Jul-Dec; prior = Jan-Jun
			return getdate(f"{y}-01-01"), getdate(f"{y}-06-30")
		# Current = Jan-Jun; prior = Jul-Dec of prev year
		return getdate(f"{y - 1}-07-01"), getdate(f"{y - 1}-12-31")
	if frequency == "Annual":
		# Prior calendar year (most LWF Acts are calendar year).
		y = today_date.year - 1
		return getdate(f"{y}-01-01"), getdate(f"{y}-12-31")
	return None, None


def _notify_lwf_due(company, state, period_start, period_end, existing_filing):
	hr_users = frappe.get_all(
		"Has Role",
		filters={"role": "HR Manager", "parenttype": "User"},
		fields=["parent"],
		distinct=True,
	)
	subject = _("LWF Return due: {0} / {1} / {2}–{3}").format(
		company, state, formatdate(period_start), formatdate(period_end)
	)
	description = _(
		"The Labour Welfare Fund return for {0} ({1}, period {2}–{3}) is due. "
		"{4} Generate via LWF Return."
	).format(
		company,
		state,
		formatdate(period_start),
		formatdate(period_end),
		(
			_("Existing draft: {0}.").format(existing_filing)
			if existing_filing
			else _("No return raised yet.")
		),
	)
	ref_dt = "LWF Return" if existing_filing else "Company"
	ref_name = existing_filing or company

	for u in hr_users:
		user = u.parent
		if user in ("Administrator", "Guest"):
			continue
		todo_exists = frappe.db.exists(
			"ToDo",
			{
				"allocated_to": user,
				"reference_type": ref_dt,
				"reference_name": ref_name,
				"description": ("like", f"%LWF due for {company}/{state}/{formatdate(period_start)}%"),
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
					"reference_type": ref_dt,
					"reference_name": ref_name,
					"description": f"LWF due for {company}/{state}/{formatdate(period_start)}–{formatdate(period_end)}: {description}",
					"priority": "High",
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"LWF ToDo creation failed for {user}",
				message=frappe.get_traceback(),
			)
		_pwa_notify(user, subject, description, ref_dt, ref_name)


def _pwa_notify(user, subject, description, ref_dt, ref_name):
	if not frappe.db.exists("DocType", "PWA Notification"):
		return
	try:
		frappe.get_doc(
			{
				"doctype": "PWA Notification",
				"to_user": user,
				"from_user": "Administrator",
				"message": f"{subject}: {description}",
				"reference_document_type": ref_dt,
				"reference_document_name": ref_name,
				"category": "Compliance",
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title=f"PWA notification failed for {user}",
			message=frappe.get_traceback(),
		)
