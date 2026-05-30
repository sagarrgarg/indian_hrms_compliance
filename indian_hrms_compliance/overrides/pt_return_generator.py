# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Professional Tax Return Generator — Phase 6B-2.

Produces a per-employee PT CSV for (Company × State × Period) by
aggregating Salary Slip PT deductions across the period. Compares
each deduction against the expected PT per Indian State.pt_slabs to
flag variance for audit.

Slab lookup honours:
  - Gender (MH has Male / Female slabs)
  - Period (Monthly / Half-yearly — TN/KL use Half-yearly slabs)
  - Special-month bump (KA / MH ₹300 in Feb)
  - 'to_amount = 0' meaning 'and above'
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
	"pt_filing_window_days": 10,
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
# Slab lookup
# ---------------------------------------------------------------------------


def _compute_expected_pt(state_doc, gross_wages, gender, period_month_int):
	"""Return the expected PT amount for one employee for one slip's worth
	of wages.

	Args:
	  state_doc: Indian State doc (with pt_slabs loaded).
	  gross_wages: employee gross for the period (monthly or half-yearly).
	  gender: 'Male' / 'Female' / 'Other' / None.
	  period_month_int: 1..12 — used to apply the 'special_month' bump in
	                    February for states like KA/MH.

	Returns 0 if no slab matches (state has PT disabled OR wages below the
	first slab)."""
	if not state_doc or not state_doc.pt_applicable:
		return 0
	if not state_doc.pt_slabs:
		return 0

	gross = flt(gross_wages)
	gender = (gender or "Any").title()

	# Filter slabs by gender — prefer specific gender over 'Any'.
	matching_gender_slabs = [s for s in state_doc.pt_slabs if (s.gender or "Any") == gender]
	if not matching_gender_slabs:
		matching_gender_slabs = [s for s in state_doc.pt_slabs if (s.gender or "Any") == "Any"]

	for slab in matching_gender_slabs:
		from_amount = flt(slab.from_amount)
		to_amount = flt(slab.to_amount)
		# to_amount = 0 means 'and above'.
		matched = (gross >= from_amount) and (to_amount == 0 or gross <= to_amount)
		if not matched:
			continue
		# Apply special-month bump (February for KA / MH).
		is_feb = period_month_int == 2
		if is_feb and flt(slab.special_month_amount) > 0:
			return flt(slab.special_month_amount)
		return flt(slab.amount)
	return 0


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


def _slip_pt_amount(slip, mapping):
	comp = mapping.pt_component if mapping else None
	if comp:
		for r in slip.get("deductions") or []:
			if r.salary_component == comp:
				return flt(r.amount)
		return 0
	# Substring fallback.
	for r in slip.get("deductions") or []:
		lower = (r.salary_component or "").lower()
		if "professional tax" in lower or lower == "pt":
			return flt(r.amount)
	return 0


def _slip_gross_earnings(slip):
	return sum(flt(r.amount) for r in (slip.get("earnings") or []))


# ---------------------------------------------------------------------------
# CSV builder
# ---------------------------------------------------------------------------


PT_CSV_HEADERS = [
	"Employee Code",
	"Employee Name",
	"PAN",
	"Gender",
	"Gross Wages",
	"PT Deducted",
	"Expected PT",
	"Variance",
	"Salary Slip",
]


def _build_pt_csv(rows):
	buf = io.StringIO()
	writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
	writer.writerow(PT_CSV_HEADERS)
	for r in rows:
		writer.writerow(
			[
				(r.get("employee") or "").strip(),
				(r.get("employee_name") or "").strip(),
				(r.get("pan") or "").strip(),
				(r.get("gender") or "").strip(),
				int(round(flt(r.get("gross_wages")))),
				int(round(flt(r.get("pt_deducted")))),
				int(round(flt(r.get("expected_pt")))),
				int(round(flt(r.get("variance")))),
				(r.get("salary_slip") or "").strip(),
			]
		)
	return buf.getvalue()


def _attach_csv(doc, csv_content, fieldname="pt_csv"):
	filename = f"{doc.name}.csv"
	existing_url = doc.get(fieldname)
	if existing_url:
		try:
			existing = frappe.db.get_value("File", {"file_url": existing_url}, "name")
			if existing:
				frappe.delete_doc("File", existing, ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"Old PT CSV cleanup failed for {doc.name}",
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
def generate_pt_return(pt_return_name):
	"""Build per-employee PT rows + CSV. Idempotent."""
	doc = frappe.get_doc("Professional Tax Return", pt_return_name)
	if doc.filing_status == "Filed":
		frappe.throw(
			_("PT Return {0} is already Filed — cancel it first.").format(doc.name)
		)
	if doc.filing_status == "Cancelled":
		frappe.throw(_("PT Return {0} is Cancelled.").format(doc.name))

	state_doc = frappe.get_doc("Indian State", doc.state)
	mapping = get_mapping_for_company(doc.company)

	# Reset rows.
	doc.set("rows", [])

	slips = _slips_in_period(doc.company, doc.period_start, doc.period_end)

	# Group by employee to roll up half-yearly periods (TN / KL).
	employee_aggregate = {}
	exceptions = []
	skipped_other_state = 0
	skipped_no_state = 0

	for slip_meta in slips:
		emp_state = resolve_employee_state(slip_meta.employee)
		if not emp_state:
			# We don't immediately fail — we add to exceptions and skip
			# (employee has no resolvable state at all). HR fixes data.
			exceptions.append(
				f"- {slip_meta.employee} ({slip_meta.employee_name}): no resolvable state. Set Address or HR Settings.default_pt_state."
			)
			skipped_no_state += 1
			continue
		if emp_state != doc.state:
			skipped_other_state += 1
			continue

		slip = frappe.get_doc("Salary Slip", slip_meta.name)
		pt = _slip_pt_amount(slip, mapping)
		gross = _slip_gross_earnings(slip)

		bucket = employee_aggregate.setdefault(
			slip.employee,
			{
				"employee": slip.employee,
				"employee_name": slip.employee_name,
				"pan": (frappe.db.get_value("Employee", slip.employee, "pan_number") or "").upper(),
				"gender": frappe.db.get_value("Employee", slip.employee, "gender") or "",
				"gross_wages": 0,
				"pt_deducted": 0,
				"slip_dates": [],
				"salary_slip": slip.name,  # last slip in the period
			},
		)
		bucket["gross_wages"] += gross
		bucket["pt_deducted"] += pt
		bucket["slip_dates"].append(getdate(slip.start_date))
		bucket["salary_slip"] = slip.name

	# Compute expected_pt + variance per aggregated employee row.
	for bucket in employee_aggregate.values():
		# Period month for special-month logic — use the first slip's month
		# (PT special month applies to that specific month's slip).
		first_month = min(bucket["slip_dates"]).month if bucket["slip_dates"] else 0
		expected = _compute_expected_pt(
			state_doc, bucket["gross_wages"], bucket["gender"], first_month
		)
		bucket["expected_pt"] = expected
		bucket["variance"] = flt(bucket["pt_deducted"]) - flt(expected)
		bucket.pop("slip_dates", None)

	rows = sorted(employee_aggregate.values(), key=lambda r: r["employee"])
	for r in rows:
		doc.append("rows", r)

	doc.total_employees_in_state = len(rows)
	doc.total_pt_collected = sum(flt(r["pt_deducted"]) for r in rows)
	doc.filing_status = "Generated"
	doc.generated_on = now()

	# Variance roll-up — log how many rows have nonzero variance.
	variance_rows = [r for r in rows if abs(flt(r["variance"])) > 0.5]
	if variance_rows:
		exceptions.append(
			f"- {len(variance_rows)} employee(s) have PT variance vs slab — review the rows table."
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

	csv_content = _build_pt_csv(rows)
	_attach_csv(doc, csv_content, fieldname="pt_csv")

	return {
		"name": doc.name,
		"total_employees_in_state": doc.total_employees_in_state,
		"total_pt_collected": doc.total_pt_collected,
		"pt_csv": doc.pt_csv,
		"variance_rows": len(variance_rows),
		"exceptions_count": len([e for e in exceptions if e]),
	}


@frappe.whitelist()
def mark_pt_return_filed(pt_return_name, challan_number=None):
	doc = frappe.get_doc("Professional Tax Return", pt_return_name)
	if doc.filing_status != "Generated":
		frappe.throw(
			_("Only Generated PT Returns can be marked as Filed. Current status: {0}").format(
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
# Daily scheduler
# ---------------------------------------------------------------------------


def send_pt_return_due_reminders():
	"""Daily — alert HR Managers when a state's PT return for the most
	recent period is unfiled and within the reminder window after period
	close. Monthly states → reminder fires day-of-period-end+1 .. +N.
	Half-yearly → same, computed against the period close."""
	window_days = int(_hr_setting("pt_filing_window_days", 10) or 10)
	td = getdate(today())

	companies = frappe.get_all("Company", fields=["name"])
	# All states with PT applicable.
	states = frappe.get_all(
		"Indian State", filters={"pt_applicable": 1}, fields=["name", "pt_filing_frequency"]
	)

	for c in companies:
		for st in states:
			period_start, period_end = _prior_pt_period(td, st.pt_filing_frequency)
			if not period_end:
				continue
			# Reminder window: period_end+1 .. period_end+window_days.
			if td < add_days(period_end, 1) or td > add_days(period_end, window_days):
				continue
			# Was there at least one slip for an employee in this state for
			# this period? (Cheap heuristic — if no slips in period for this
			# company at all, skip.)
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
			# Has a return been raised + Filed?
			existing = frappe.db.exists(
				"Professional Tax Return",
				{
					"company": c.name,
					"state": st.name,
					"period_start": period_start,
					"period_end": period_end,
					"filing_status": ("!=", "Cancelled"),
				},
			)
			if existing and frappe.db.get_value("Professional Tax Return", existing, "filing_status") == "Filed":
				continue
			_notify_pt_due(c.name, st.name, period_start, period_end, existing)


def _prior_pt_period(today_date, frequency):
	"""Return (period_start, period_end) for the *prior* PT filing period
	relative to today_date. Half-yearly buckets are Apr-Sep / Oct-Mar."""
	if not frequency:
		return None, None
	if frequency == "Monthly":
		this_start = get_first_day(today_date)
		prior_start = get_first_day(add_months(this_start, -1))
		prior_end = get_last_day(prior_start)
		return prior_start, prior_end
	if frequency == "Half-yearly":
		# Determine which half-year today is in, return the prior one.
		m = today_date.month
		y = today_date.year
		if m >= 4 and m <= 9:
			# Current half = Apr-Sep; prior = Oct(prev)-Mar(curr)
			return getdate(f"{y - 1}-10-01"), getdate(f"{y}-03-31")
		# Current half = Oct-Mar (straddles); prior = Apr-Sep current OR previous year
		if m >= 10:
			return getdate(f"{y}-04-01"), getdate(f"{y}-09-30")
		# Jan-Mar — current half is Oct(prev)-Mar(curr); prior = Apr-Sep(prev)
		return getdate(f"{y - 1}-04-01"), getdate(f"{y - 1}-09-30")
	# Annual not used for PT — fallthrough.
	return None, None


def _notify_pt_due(company, state, period_start, period_end, existing_filing):
	hr_users = frappe.get_all(
		"Has Role",
		filters={"role": "HR Manager", "parenttype": "User"},
		fields=["parent"],
		distinct=True,
	)
	subject = _("PT Return due: {0} / {1} / {2}–{3}").format(
		company, state, formatdate(period_start), formatdate(period_end)
	)
	description = _(
		"The Professional Tax return for {0} ({1}, period {2}–{3}) is due. "
		"{4} Generate via Professional Tax Return."
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
	ref_dt = "Professional Tax Return" if existing_filing else "Company"
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
				"description": ("like", f"%PT due for {company}/{state}/{formatdate(period_start)}%"),
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
					"description": f"PT due for {company}/{state}/{formatdate(period_start)}–{formatdate(period_end)}: {description}",
					"priority": "High",
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"PT ToDo creation failed for {user}",
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
