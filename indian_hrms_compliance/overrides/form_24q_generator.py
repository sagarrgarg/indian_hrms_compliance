# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Form 24Q / Form 138 Generator — Phase 6B-2.

Produces the quarterly TDS-on-salary statement file for a given
(Company × Fiscal Year × Quarter) from submitted Salary Slips.

The file format we emit is a *simplified RPU input file* — a pipe-
delimited (^) text per the broad NSDL TIN RPU spec, divided into
four logical line types:

  FH  — File Header     (1 row, file metadata)
  BH  — Batch Header    (1 row per statement; here 1)
  CH  — Challan Header  (1 per challan)
  DD  — Deductee Detail (1 per Salary Slip TDS attribution)
  SD  — Salary Detail   (Annexure II; Q4 only, 1 per employee)

Each row is prefixed with a 2-char record type and a running line
number. Numeric amounts are rendered as integer rupees (RPU rejects
decimals in most amount fields). HR runs the offline NSDL RPU
utility against this .txt to produce the .fvu for upload.

The DEDUCTEE PAN column is mandatory; employees without PAN are
skipped and logged in exceptions (with the option to override via
the reason_for_lower_no_deduction code in a future iteration).

Tax computation for Annexure II:
  We pull each employee's Salary Slips for the *full FY* and aggregate:
    gross_salary = sum of all earnings amounts
    section_10_exemptions = HRA + LTA + conveyance (heuristic — substring)
    section_16_deductions = ₹75,000 standard (new regime FY 2026-27) +
                            PT deducted in the FY
    tds_deducted = sum of Income Tax Component deductions
  This is intentionally approximate — the Income Tax Computation report
  in ERPNext does the exact math; we re-derive directly from slips so
  Q4 generation works even without that report enabled.
"""

from datetime import date

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
from indian_hrms_compliance.payroll.doctype.tds_return_form_24q.tds_return_form_24q import (
	get_quarter_dates,
)


# RPU file delimiter — caret per NSDL spec.
FIELD_SEP = "^"
LINE_SEP = "\n"

# Default Section 16 standard deduction under the new regime, FY 2026-27.
# (Old regime: ₹50,000.) Generator uses new-regime by default; old regime
# users can override Annexure II values after generation via the grid.
SEC_16_STD_DEDUCTION = 75000

# Filing window default (days after quarter end) — used by the scheduler.
HR_SETTINGS_DEFAULTS = {
	"form_24q_filing_window_days": 30,
	"pt_filing_window_days": 10,
	"lwf_filing_window_days": 15,
}


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
# Salary Slip + employee aggregations
# ---------------------------------------------------------------------------


def _get_submitted_slips_for_period(company, period_start, period_end):
	"""Return submitted Salary Slip names whose start_date falls inside
	[period_start, period_end]."""
	return frappe.get_all(
		"Salary Slip",
		filters={
			"company": company,
			"docstatus": 1,
			"start_date": (">=", period_start),
			"start_date": ("<=", period_end),
		},
		fields=["name", "employee", "employee_name", "start_date", "end_date", "gross_pay"],
		order_by="employee, start_date",
	)


def _income_tax_component_amount(slip, mapping):
	"""Pull the TDS / Income Tax deduction amount from the slip. Mapping-
	first, then substring fallback ('Income Tax' / 'TDS')."""
	comp = mapping.income_tax_component if mapping else None
	if comp:
		for r in slip.get("deductions") or []:
			if r.salary_component == comp:
				return flt(r.amount)
		return 0
	for r in slip.get("deductions") or []:
		lower = (r.salary_component or "").lower()
		if "income tax" in lower or "tds" in lower:
			return flt(r.amount)
	return 0


def _pt_component_amount(slip, mapping):
	comp = mapping.pt_component if mapping else None
	if comp:
		for r in slip.get("deductions") or []:
			if r.salary_component == comp:
				return flt(r.amount)
		return 0
	for r in slip.get("deductions") or []:
		lower = (r.salary_component or "").lower()
		if "professional tax" in lower or lower == "pt":
			return flt(r.amount)
	return 0


def _slip_gross_earnings(slip):
	return sum(flt(r.amount) for r in (slip.get("earnings") or []))


# ---------------------------------------------------------------------------
# Annexure I — quarterly deductee rows
# ---------------------------------------------------------------------------


def _build_annexure_i_rows(doc, mapping, slips_meta):
	"""One row per Salary Slip that has a non-zero TDS line. Employees
	without PAN are skipped and logged."""
	rows = []
	exceptions = []
	skipped_no_pan = 0
	skipped_zero_tds = 0
	# Resolve the default challan (first challan attached to the doc, if
	# any) so we can pre-populate the challan_serial_no — HR can re-attribute
	# manually in the grid post-generation.
	default_challan_serial = doc.challans[0].challan_serial_no if doc.challans else ""

	for slip_meta in slips_meta:
		slip = frappe.get_doc("Salary Slip", slip_meta.name)
		tds = _income_tax_component_amount(slip, mapping)
		if not tds:
			skipped_zero_tds += 1
			continue
		pan = frappe.db.get_value("Employee", slip.employee, "pan_number") or ""
		if not pan:
			exceptions.append(
				f"- {slip.employee} ({slip.employee_name}): no PAN on Employee master — skipped from Annexure I (TDS ₹{int(round(tds))} not declared)."
			)
			skipped_no_pan += 1
			continue
		rows.append(
			{
				"employee": slip.employee,
				"employee_pan": pan.upper(),
				"employee_name": slip.employee_name,
				"payment_date": slip.end_date or slip.start_date,
				"amount_paid": _slip_gross_earnings(slip),
				"tds_amount": tds,
				"challan_serial_no": default_challan_serial,
				"section_code": "192A",
				"reason_for_lower_no_deduction": "",
				"salary_slip": slip.name,
			}
		)
	return rows, exceptions, skipped_no_pan, skipped_zero_tds


# ---------------------------------------------------------------------------
# Annexure II — Q4 annual salary breakup
# ---------------------------------------------------------------------------


def _employee_fy_slips(company, employee, fy_start, fy_end):
	return frappe.get_all(
		"Salary Slip",
		filters={
			"company": company,
			"employee": employee,
			"docstatus": 1,
			"start_date": (">=", fy_start),
			"start_date": ("<=", fy_end),
		},
		fields=["name"],
		order_by="start_date",
	)


def _estimate_section_10_exemptions(slip):
	"""Heuristic — sum of HRA / LTA / Conveyance earnings. The real Form
	24Q Annexure II uses the year-end declared exemption; we approximate
	from slips. HR can override values in the grid post-generation."""
	total = 0
	for r in slip.get("earnings") or []:
		lower = (r.salary_component or "").lower()
		if "hra" in lower or "house rent" in lower:
			# Not all HRA paid is exempt — RoT is 40-50% depending on city +
			# rent receipt. We estimate 40% as a starting point; HR overrides.
			total += flt(r.amount) * 0.40
		elif "lta" in lower or "leave travel" in lower:
			total += flt(r.amount)
		elif "conveyance" in lower or "transport allowance" in lower:
			total += flt(r.amount)
	return total


def _build_annexure_ii_rows(doc, mapping, fy_start, fy_end):
	"""For each distinct employee in the FY, compute aggregate salary +
	tax breakup. Skips employees with no PAN (consistent with Annex I)."""
	rows = []
	exceptions = []
	skipped_no_pan = 0

	# Distinct employees with at least one submitted slip in the FY.
	employees = frappe.db.sql(
		"""
		SELECT DISTINCT employee
		FROM `tabSalary Slip`
		WHERE company = %s
		  AND docstatus = 1
		  AND start_date >= %s
		  AND start_date <= %s
		""",
		(doc.company, fy_start, fy_end),
		as_dict=True,
	)

	for emp_row in employees:
		emp = emp_row.employee
		emp_doc = frappe.db.get_value(
			"Employee", emp, ["employee_name", "pan_number"], as_dict=True
		) or {}
		pan = (emp_doc.get("pan_number") or "").upper()
		if not pan:
			exceptions.append(
				f"- {emp} ({emp_doc.get('employee_name')}): no PAN — skipped from Annexure II."
			)
			skipped_no_pan += 1
			continue

		# Aggregate slips for the FY.
		slips = _employee_fy_slips(doc.company, emp, fy_start, fy_end)
		gross_salary = 0
		section_10 = 0
		pt_paid = 0
		tds = 0
		for s_meta in slips:
			slip = frappe.get_doc("Salary Slip", s_meta.name)
			gross_salary += _slip_gross_earnings(slip)
			section_10 += _estimate_section_10_exemptions(slip)
			pt_paid += _pt_component_amount(slip, mapping)
			tds += _income_tax_component_amount(slip, mapping)

		# Section 16 = std deduction + PT (under both regimes PT is allowed
		# u/s 16(iii)).
		section_16 = SEC_16_STD_DEDUCTION + pt_paid
		income_under_salaries = max(gross_salary - section_10 - section_16, 0)
		gross_total_income = income_under_salaries  # other_income unknown at HR end
		taxable_income = gross_total_income  # Chapter VI-A unknown; HR overrides
		# Tax computation: leave to HR — set tax_payable = tds (so liability ≈
		# deducted and tds_balance = 0). HR can refine via the grid.
		rows.append(
			{
				"employee": emp,
				"employee_pan": pan,
				"employee_name": emp_doc.get("employee_name"),
				"gross_salary": gross_salary,
				"section_10_exemptions": section_10,
				"section_16_deductions": section_16,
				"income_under_salaries": income_under_salaries,
				"other_income": 0,
				"gross_total_income": gross_total_income,
				"chapter_via_deductions": 0,
				"taxable_income": taxable_income,
				"tax_payable": tds,
				"surcharge": 0,
				"health_education_cess": 0,
				"tax_liability": tds,
				"tds_deducted": tds,
				"tds_balance": 0,
			}
		)
	return rows, exceptions, skipped_no_pan


# ---------------------------------------------------------------------------
# RPU .txt file builder
# ---------------------------------------------------------------------------


def _rpu_int(amount):
	"""Render an amount as integer rupees per RPU spec (no decimals in
	most amount columns)."""
	return str(int(round(flt(amount))))


def _build_rpu_txt(doc):
	"""Build the simplified RPU input file. Each record is prefixed with
	a 2-char record type ('FH', 'BH', 'CH', 'DD', 'SD') and a sequential
	line number. All records are caret-separated.

	NOTE: full NSDL RPU spec has 40+ optional columns per record; we emit
	the *minimum required* set so the file parses cleanly. RPU will warn
	on missing optional fields but accept the file."""
	lines = []
	line_no = 1

	# --- File Header (FH) ---
	fh = [
		"FH",
		str(line_no),
		"24Q" if doc.form_name != "Form 138" else "138",
		doc.fiscal_year or "",
		doc.quarter or "",
		"R" if doc.filing_status == "Filed" else "O",  # R=Revised, O=Original
		doc.employer_tan or "",
		doc.employer_pan or "",
		doc.company or "",
		(doc.responsible_person_name or "").strip(),
		(doc.responsible_person_pan or "").strip(),
		(doc.responsible_person_designation or "").strip(),
		(doc.responsible_person_address or "").replace("\n", " ").strip(),
	]
	lines.append(FIELD_SEP.join(_sanitise(c) for c in fh))
	line_no += 1

	# --- Batch Header (BH) ---
	bh = [
		"BH",
		str(line_no),
		"1",  # batch number
		doc.name,
		str(len(doc.challans or [])),
		str(len(doc.annexure_i_rows or [])),
		_rpu_int(doc.total_tax_deducted),
		_rpu_int(doc.total_tax_deposited),
	]
	lines.append(FIELD_SEP.join(_sanitise(c) for c in bh))
	line_no += 1

	# --- Challan Headers (CH) ---
	# Map challan_serial_no → line_no so DD rows can backreference.
	challan_line_map = {}
	for idx, ch in enumerate(doc.challans or [], start=1):
		ch_row = [
			"CH",
			str(line_no),
			str(idx),
			(ch.challan_serial_no or "").strip(),
			(ch.bsr_code or "").strip(),
			(ch.challan_date.strftime("%d%m%Y") if ch.challan_date else ""),
			_rpu_int(ch.challan_amount),
			_rpu_int(ch.challan_total_tds),
			(ch.section_code or "192").strip(),
			(ch.bank_name or "").strip(),
		]
		lines.append(FIELD_SEP.join(_sanitise(c) for c in ch_row))
		challan_line_map[ch.challan_serial_no or ""] = idx
		line_no += 1

	# --- Deductee Details (DD) — Annexure I ---
	for idx, dd in enumerate(doc.annexure_i_rows or [], start=1):
		challan_no = challan_line_map.get(dd.challan_serial_no or "", "")
		dd_row = [
			"DD",
			str(line_no),
			str(idx),
			str(challan_no),
			(dd.employee_pan or "").upper().strip(),
			(dd.employee_name or "").strip()[:75],
			(dd.payment_date.strftime("%d%m%Y") if dd.payment_date else ""),
			_rpu_int(dd.amount_paid),
			_rpu_int(dd.tds_amount),
			(dd.section_code or "192A").strip(),
			(dd.reason_for_lower_no_deduction or "").strip(),
			(dd.employee or "").strip(),
		]
		lines.append(FIELD_SEP.join(_sanitise(c) for c in dd_row))
		line_no += 1

	# --- Salary Details (SD) — Annexure II (Q4 only) ---
	if doc.quarter == "Q4" and (doc.annexure_ii_rows or []):
		for idx, sd in enumerate(doc.annexure_ii_rows or [], start=1):
			sd_row = [
				"SD",
				str(line_no),
				str(idx),
				(sd.employee_pan or "").upper().strip(),
				(sd.employee_name or "").strip()[:75],
				_rpu_int(sd.gross_salary),
				_rpu_int(sd.section_10_exemptions),
				_rpu_int(sd.section_16_deductions),
				_rpu_int(sd.income_under_salaries),
				_rpu_int(sd.other_income),
				_rpu_int(sd.gross_total_income),
				_rpu_int(sd.chapter_via_deductions),
				_rpu_int(sd.taxable_income),
				_rpu_int(sd.tax_payable),
				_rpu_int(sd.surcharge),
				_rpu_int(sd.health_education_cess),
				_rpu_int(sd.tax_liability),
				_rpu_int(sd.tds_deducted),
				_rpu_int(sd.tds_balance),
			]
			lines.append(FIELD_SEP.join(_sanitise(c) for c in sd_row))
			line_no += 1

	return LINE_SEP.join(lines) + LINE_SEP


def _sanitise(val):
	"""Strip embedded delimiters defensively. RPU rejects rows whose
	column count is off; an unescaped ^ inside Name would shift columns."""
	if val is None:
		return ""
	return str(val).replace(FIELD_SEP, " ").replace("\r", " ").replace("\n", " ").strip()


def _attach_txt_file(doc, txt_content):
	filename = f"{doc.name}.txt"
	if doc.txt_file:
		try:
			existing = frappe.db.get_value("File", {"file_url": doc.txt_file}, "name")
			if existing:
				frappe.delete_doc("File", existing, ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"Old 24Q txt cleanup failed for {doc.name}",
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
			"attached_to_field": "txt_file",
		}
	).insert(ignore_permissions=True)
	doc.db_set("txt_file", file_doc.file_url)
	return file_doc.file_url


# ---------------------------------------------------------------------------
# Whitelisted entry points
# ---------------------------------------------------------------------------


@frappe.whitelist()
def generate_form_24q(form_24q_name):
	"""Build Annexure I (and Annexure II for Q4), totals, and the RPU
	.txt file. Idempotent — reruns wipe Annexure rows and regenerate.

	Challans on the doc are PRESERVED across regeneration (HR enters them
	manually based on actual OLTAS/e-pay receipts; we never auto-create)."""
	doc = frappe.get_doc("TDS Return Form 24Q", form_24q_name)
	if doc.filing_status == "Filed":
		frappe.throw(
			_("TDS Return {0} is already Filed — cancel it first to regenerate.").format(doc.name)
		)
	if doc.filing_status == "Cancelled":
		frappe.throw(_("TDS Return {0} is Cancelled.").format(doc.name))

	mapping = get_mapping_for_company(doc.company)

	# Resolve quarter date range.
	q_start, q_end = get_quarter_dates(doc.fiscal_year, doc.quarter)

	# Reset Annexure tables (preserve challans).
	doc.set("annexure_i_rows", [])
	doc.set("annexure_ii_rows", [])

	slips = _get_submitted_slips_for_period(doc.company, q_start, q_end)
	rows_i, exc_i, skipped_no_pan_i, skipped_zero_tds = _build_annexure_i_rows(doc, mapping, slips)
	for r in rows_i:
		doc.append("annexure_i_rows", r)

	exc_ii = []
	skipped_no_pan_ii = 0
	if doc.quarter == "Q4":
		# FY start/end — use Fiscal Year master.
		fy_start = frappe.db.get_value("Fiscal Year", doc.fiscal_year, "year_start_date")
		fy_end = frappe.db.get_value("Fiscal Year", doc.fiscal_year, "year_end_date")
		rows_ii, exc_ii, skipped_no_pan_ii = _build_annexure_ii_rows(doc, mapping, fy_start, fy_end)
		for r in rows_ii:
			doc.append("annexure_ii_rows", r)

	# Totals.
	doc.total_tax_deducted = sum(flt(r.tds_amount) for r in doc.annexure_i_rows)
	doc.total_tax_deposited = sum(flt(r.challan_total_tds) for r in (doc.challans or []))
	doc.total_employees = len({r.employee for r in doc.annexure_i_rows})

	# Challan reconciliation — warn (don't block) when totals diverge.
	exceptions = []
	exceptions.extend(exc_i)
	exceptions.extend(exc_ii)
	if doc.challans and doc.total_tax_deposited != doc.total_tax_deducted:
		exceptions.append(
			f"- Challan reconciliation: tax_deducted (₹{int(round(doc.total_tax_deducted))}) ≠ "
			f"tax_deposited (₹{int(round(doc.total_tax_deposited))}). Add/adjust challan rows or check Annexure I attributions."
		)
	if not doc.challans:
		exceptions.append(
			"- No challan rows entered. RPU will reject the .fvu without challan attribution. "
			"Add a Form 24Q Challan row before filing."
		)
	if skipped_zero_tds:
		exceptions.append(
			f"- {skipped_zero_tds} salary slip(s) had zero TDS — excluded from Annexure I (normal for low-income employees)."
		)
	if skipped_no_pan_i:
		exceptions.append(
			f"- {skipped_no_pan_i} employee(s) skipped from Annexure I due to missing PAN."
		)
	if skipped_no_pan_ii:
		exceptions.append(
			f"- {skipped_no_pan_ii} employee(s) skipped from Annexure II due to missing PAN."
		)
	if not doc.annexure_i_rows:
		exceptions.append(
			"- Annexure I is empty — no submitted Salary Slips with TDS for this quarter."
		)
	doc.exceptions = "\n".join(exceptions) if exceptions else ""

	doc.filing_status = "Generated"
	doc.generated_on = now()
	doc.save(ignore_permissions=True)

	# Build + attach the RPU .txt.
	txt_content = _build_rpu_txt(doc)
	_attach_txt_file(doc, txt_content)

	return {
		"name": doc.name,
		"total_employees": doc.total_employees,
		"total_tax_deducted": doc.total_tax_deducted,
		"total_tax_deposited": doc.total_tax_deposited,
		"txt_file": doc.txt_file,
		"annexure_i_count": len(doc.annexure_i_rows),
		"annexure_ii_count": len(doc.annexure_ii_rows or []),
		"exceptions_count": len([e for e in exceptions if e]),
	}


@frappe.whitelist()
def mark_form_24q_filed(form_24q_name, ack_number):
	"""Capture acknowledgement number + flip to Filed."""
	doc = frappe.get_doc("TDS Return Form 24Q", form_24q_name)
	if doc.filing_status != "Generated":
		frappe.throw(
			_("Only Generated TDS Returns can be marked as Filed. Current status: {0}").format(
				doc.filing_status
			)
		)
	if not ack_number:
		frappe.throw(_("Acknowledgement number is required to mark as Filed."))
	doc.filing_status = "Filed"
	doc.filed_on = nowdate()
	doc.ack_number = ack_number
	doc.save(ignore_permissions=True)
	return doc.name


# ---------------------------------------------------------------------------
# Daily scheduler — Form 24Q due reminders
# ---------------------------------------------------------------------------


# Statutory Form 24Q due dates: Q1 → 31 Jul; Q2 → 31 Oct; Q3 → 31 Jan;
# Q4 → 31 May. The "reminder window" opens N days BEFORE the due date.
QUARTER_DUE_DATE_OFFSETS = {
	"Q1": ("07-31", 0),  # Apr-Jun quarter; due July 31
	"Q2": ("10-31", 0),  # Jul-Sep quarter; due October 31
	"Q3": ("01-31", 1),  # Oct-Dec quarter; due January 31 of *next* year
	"Q4": ("05-31", 1),  # Jan-Mar quarter; due May 31 of *next* year
}


def _quarter_due_date(fiscal_year, quarter):
	"""Resolve the statutory due date for a (FY, Quarter)."""
	if quarter not in QUARTER_DUE_DATE_OFFSETS:
		return None
	month_day, year_offset = QUARTER_DUE_DATE_OFFSETS[quarter]
	fy_start = frappe.db.get_value("Fiscal Year", fiscal_year, "year_start_date")
	if not fy_start:
		return None
	fy_start = getdate(fy_start)
	due_year = fy_start.year + year_offset
	return getdate(f"{due_year}-{month_day}")


def send_form_24q_due_reminders():
	"""Daily — alert HR Managers when a quarter's TDS return is due in
	`form_24q_filing_window_days` days OR overdue and no return exists."""
	window_days = int(_hr_setting("form_24q_filing_window_days", 30) or 30)
	td = getdate(today())

	companies = frappe.get_all("Company", fields=["name"])
	# Iterate current + previous FY to catch Q4 (which closes well after the
	# FY end).
	fiscal_years = frappe.get_all(
		"Fiscal Year",
		fields=["name"],
		filters={
			"year_start_date": ("<=", td),
			"year_end_date": (">=", add_days(td, -365)),
		},
	)

	for c in companies:
		for fy in fiscal_years:
			for q in ("Q1", "Q2", "Q3", "Q4"):
				due = _quarter_due_date(fy.name, q)
				if not due:
					continue
				# Reminder window: due - window_days .. due + window_days.
				if td < add_days(due, -window_days) or td > add_days(due, window_days):
					continue
				# Did the quarter end yet? If not, skip.
				q_start, q_end = get_quarter_dates(fy.name, q)
				if td <= q_end:
					continue
				# Is there a Filed return already?
				existing = frappe.db.exists(
					"TDS Return Form 24Q",
					{
						"company": c.name,
						"fiscal_year": fy.name,
						"quarter": q,
						"filing_status": ("!=", "Cancelled"),
					},
				)
				if existing:
					status = frappe.db.get_value("TDS Return Form 24Q", existing, "filing_status")
					if status == "Filed":
						continue
				_notify_24q_due(c.name, fy.name, q, due, existing)


def _notify_24q_due(company, fiscal_year, quarter, due_date, existing_filing):
	hr_users = frappe.get_all(
		"Has Role",
		filters={"role": "HR Manager", "parenttype": "User"},
		fields=["parent"],
		distinct=True,
	)
	subject = _("Form 24Q due: {0} / {1} / {2} — by {3}").format(
		company, fiscal_year, quarter, formatdate(due_date)
	)
	description = _(
		"The quarterly TDS-on-salary return for {0} ({1} {2}) is due by {3}. "
		"{4} Generate and file via TDS Return Form 24Q."
	).format(
		company,
		fiscal_year,
		quarter,
		formatdate(due_date),
		(
			_("Existing draft: {0}.").format(existing_filing)
			if existing_filing
			else _("No return raised yet.")
		),
	)
	ref_dt = "TDS Return Form 24Q" if existing_filing else "Company"
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
				"description": ("like", f"%Form 24Q due for {company}/{fiscal_year}/{quarter}%"),
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
					"description": f"Form 24Q due for {company}/{fiscal_year}/{quarter} by {formatdate(due_date)}: {description}",
					"priority": "High",
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"24Q ToDo creation failed for {user}",
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
