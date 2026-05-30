# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Phase 4 doc_event additions to Full and Final Statement.

Adds notice-period math, auto-creation of Gratuity / Leave Encashment
drafts, and TDS-on-FnF computation. Kept out of the core FullandFinal
Statement class so upstream diffs stay clean.

Wired in hooks.py under doc_events["Full and Final Statement"].
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

NOTICE_RECOVERY_COMPONENT = "Notice Period Shortfall"
PAY_IN_LIEU_COMPONENT = "Pay in Lieu of Notice"
TDS_COMPONENT = "TDS on Final Settlement"


def _hr_setting(field, default=None):
	"""Safe HR Settings read — returns default if the field doesn't exist
	yet. Lets Stage 4 ship cleanly before Stage 7 wires the toggles."""
	meta = frappe.get_meta("HR Settings")
	if not meta.get_field(field):
		return default
	val = frappe.db.get_single_value("HR Settings", field)
	return default if val in (None, "") else val


def link_resignation_request(doc, method=None):
	"""before_save: if resignation_request not set, find one for this
	Employee + Company in Approved state and link it. Auto-link is best-
	effort; HR can pick a different one manually."""
	if doc.get("resignation_request"):
		return
	if not (doc.employee and doc.company):
		return
	rr = frappe.db.get_value(
		"Resignation Request",
		{
			"employee": doc.employee,
			"company": doc.company,
			"workflow_state": "Approved",
		},
		"name",
		order_by="submission_date desc",
	)
	if rr:
		doc.resignation_request = rr


def compute_phase4_lines(doc, method=None):
	"""validate: link the Resignation Request, then recompute the notice
	math + ensure auto-derived rows are present. Idempotent — won't
	duplicate component rows on re-save."""
	link_resignation_request(doc)
	_compute_notice_math(doc)
	_apply_notice_line(doc)
	_apply_auto_gratuity_line(doc)
	_apply_auto_leave_encashment_lines(doc)
	_apply_tds_line(doc)
	_recompute_totals(doc)


def _compute_notice_math(doc):
	"""Populate notice_served / balance / per-day / amount fields."""
	if not doc.resignation_request:
		# Nothing to compute — clear stale auto values.
		doc.notice_served_days = 0
		doc.notice_balance_days = 0
		doc.per_day_basic_for_recovery = 0
		doc.notice_balance_amount = 0
		return

	rr = frappe.db.get_value(
		"Resignation Request",
		doc.resignation_request,
		[
			"submission_date",
			"notice_required_days",
			"notice_disposition",
			"intended_last_working_date",
		],
		as_dict=True,
	)
	if not rr:
		return

	doc.notice_required_days = rr.notice_required_days or 0

	relieving = doc.relieving_date or rr.intended_last_working_date
	if relieving and rr.submission_date:
		served = (getdate(relieving) - getdate(rr.submission_date)).days
		doc.notice_served_days = max(served, 0)
	else:
		doc.notice_served_days = 0

	doc.notice_balance_days = (doc.notice_required_days or 0) - (doc.notice_served_days or 0)

	# Per-day rate from last Salary Slip basic
	doc.per_day_basic_for_recovery = _per_day_rate(doc.employee)

	# Signed amount: positive = recovery, negative = pay-in-lieu owed to employee
	balance_days = doc.notice_balance_days or 0
	per_day = flt(doc.per_day_basic_for_recovery)
	if rr.notice_disposition == "Short Notice (recovery)" and balance_days > 0:
		doc.notice_balance_amount = balance_days * per_day
	elif rr.notice_disposition == "Pay in Lieu of Notice" and balance_days > 0:
		# Employer waives served notice and pays equivalent → payable to employee.
		doc.notice_balance_amount = -(balance_days * per_day)
	else:
		doc.notice_balance_amount = 0


def _per_day_rate(employee):
	"""HR Settings.notice_recovery_basis decides which component(s) make up
	the daily rate; days-in-month is HR Settings.notice_recovery_days_in_month
	(default 30). Falls back to 0 silently when no salary slip exists."""
	basis = _hr_setting("notice_recovery_basis", "Basic Only")
	divisor = int(_hr_setting("notice_recovery_days_in_month", 30) or 30) or 30

	last_slip = frappe.db.get_value(
		"Salary Slip",
		{"employee": employee, "docstatus": 1},
		"name",
		order_by="start_date desc",
	)
	if not last_slip:
		return 0

	slip = frappe.get_doc("Salary Slip", last_slip)
	earnings = slip.earnings or []

	if basis == "Gross":
		amount = flt(slip.gross_pay)
	elif basis == "Basic + DA":
		amount = sum(
			flt(e.amount) for e in earnings if e.salary_component in ("Basic", "Dearness Allowance", "DA")
		)
	else:  # Basic Only
		amount = sum(flt(e.amount) for e in earnings if e.salary_component == "Basic")

	return flt(amount) / divisor if divisor else 0


def _apply_notice_line(doc):
	"""Add / remove / update the Notice Period Shortfall row in receivables
	or Pay in Lieu in payables based on notice_balance_amount and disposition.

	HR override negotiated_waiver_amount, if set and allowed, replaces the
	auto computation on the line."""
	if not doc.resignation_request:
		return

	rr_disp = frappe.db.get_value(
		"Resignation Request", doc.resignation_request, "notice_disposition"
	)

	# Decide effective amount on the line. Negotiated waiver wins if non-zero
	# and HR Settings allows it.
	allow_override = int(_hr_setting("allow_negotiated_notice_waiver", 0) or 0)
	effective_amount = flt(doc.notice_balance_amount)
	if allow_override and doc.get("negotiated_waiver_amount") not in (None, 0):
		# Override carries the sign convention from notice_balance_amount.
		sign = -1 if effective_amount < 0 else 1
		effective_amount = sign * abs(flt(doc.negotiated_waiver_amount))

	# Short Notice (recovery): line lives in receivables
	if rr_disp == "Short Notice (recovery)" and effective_amount > 0:
		_upsert_component_line(
			doc, "receivables", NOTICE_RECOVERY_COMPONENT, abs(effective_amount)
		)
		_remove_component_line(doc, "payables", PAY_IN_LIEU_COMPONENT)
	# Pay in Lieu: payable to employee, lives in payables
	elif rr_disp == "Pay in Lieu of Notice" and effective_amount < 0:
		_upsert_component_line(
			doc, "payables", PAY_IN_LIEU_COMPONENT, abs(effective_amount)
		)
		_remove_component_line(doc, "receivables", NOTICE_RECOVERY_COMPONENT)
	else:
		# Will Serve in Full / Garden Leave — no notice line either side.
		_remove_component_line(doc, "receivables", NOTICE_RECOVERY_COMPONENT)
		_remove_component_line(doc, "payables", PAY_IN_LIEU_COMPONENT)


def _apply_auto_gratuity_line(doc):
	"""If HR Settings.auto_create_gratuity_on_fnf is on, and tenure ≥ rule
	minimum, and no Gratuity already exists for this Employee, create a
	Gratuity draft and add the row to payables.

	Idempotent — won't duplicate if a Gratuity already exists OR if the
	payables already has a Gratuity row."""
	if not int(_hr_setting("auto_create_gratuity_on_fnf", 0) or 0):
		return
	if not (doc.employee and doc.relieving_date):
		return
	# Already has a Gratuity row in payables (HR added it)? skip.
	if _has_component_line(doc, "payables", "Gratuity"):
		return
	# Already has any Gratuity for this Employee? skip.
	existing = frappe.db.exists(
		"Gratuity", {"employee": doc.employee, "docstatus": ("!=", 2)}
	)
	if existing:
		# Reference the existing one in the row.
		amount = frappe.db.get_value("Gratuity", existing, "amount")
		_upsert_component_line(
			doc, "payables", "Gratuity", amount, ref_type="Gratuity", ref_name=existing
		)
		return

	# Find a Gratuity Rule for this Company (or the first one in the DB).
	rule = frappe.db.get_value(
		"Gratuity Rule", {"company": doc.company}, "name"
	) or frappe.db.get_value("Gratuity Rule", {}, "name")
	if not rule:
		# No rule configured — skip silently. HR can add manually.
		return

	try:
		gratuity = frappe.get_doc(
			{
				"doctype": "Gratuity",
				"employee": doc.employee,
				"company": doc.company,
				"posting_date": doc.relieving_date,
				"gratuity_rule": rule,
			}
		)
		gratuity.insert(ignore_permissions=True)
		_upsert_component_line(
			doc, "payables", "Gratuity", gratuity.amount,
			ref_type="Gratuity", ref_name=gratuity.name,
		)
	except Exception:
		# Tenure < minimum, no salary slip, no applicable components — all valid
		# reasons Gratuity won't compute. Don't block FnF; HR can add manually.
		frappe.log_error(
			title=f"Auto-Gratuity failed for FnF {doc.name or '(new)'}",
			message=frappe.get_traceback(),
		)


def _apply_auto_leave_encashment_lines(doc):
	"""If HR Settings.auto_create_leave_encashment_on_fnf is on, create a
	Leave Encashment draft per leave type with allow_encashment=1 that has
	a positive balance for this Employee.

	Adds one payables row per Encashment doc."""
	if not int(_hr_setting("auto_create_leave_encashment_on_fnf", 0) or 0):
		return
	if not (doc.employee and doc.relieving_date):
		return

	leave_types = frappe.get_all("Leave Type", filters={"allow_encashment": 1}, pluck="name")
	if not leave_types:
		return

	for lt in leave_types:
		# Skip if already has a Leave Encashment row for this leave type.
		if _has_component_line_with_ref(doc, "payables", "Leave Encashment", lt):
			continue
		# Skip if already has an Encashment for this Employee + leave type that's not cancelled.
		existing = frappe.db.exists(
			"Leave Encashment",
			{"employee": doc.employee, "leave_type": lt, "docstatus": ("!=", 2)},
		)
		if existing:
			amount = frappe.db.get_value("Leave Encashment", existing, "encashment_amount")
			_upsert_component_line(
				doc, "payables", "Leave Encashment", amount,
				ref_type="Leave Encashment", ref_name=existing,
			)
			continue

		# Find a Leave Allocation for this Employee + leave type whose period
		# is current or most recent.
		alloc = frappe.db.get_value(
			"Leave Allocation",
			{"employee": doc.employee, "leave_type": lt, "docstatus": 1},
			"name",
			order_by="to_date desc",
		)
		if not alloc:
			continue
		alloc_doc = frappe.db.get_value(
			"Leave Allocation",
			alloc,
			["leave_period", "to_date"],
			as_dict=True,
		)
		try:
			le = frappe.get_doc(
				{
					"doctype": "Leave Encashment",
					"employee": doc.employee,
					"leave_type": lt,
					"leave_period": alloc_doc.leave_period,
					"encashment_date": doc.relieving_date,
				}
			)
			le.insert(ignore_permissions=True)
			if flt(le.encashment_amount) > 0:
				_upsert_component_line(
					doc, "payables", "Leave Encashment", le.encashment_amount,
					ref_type="Leave Encashment", ref_name=le.name,
				)
		except Exception:
			# Most common cause: no Salary Structure / no encashable balance.
			# Don't block FnF.
			frappe.log_error(
				title=f"Auto-Leave Encashment failed for FnF {doc.name or '(new)'} / {lt}",
				message=frappe.get_traceback(),
			)


def _apply_tds_line(doc):
	"""If HR Settings.compute_tds_on_fnf is on, compute TDS on FnF using
	the Employee's Income Tax Slab and add to receivables.

	Pragmatic formula:
	  TDS_on_FnF = projected_annual_tax − YTD_TDS_deducted
	where projected_annual_tax applies the slab to (YTD taxable income +
	FnF gross payables − FnF exempt components).

	Skipped silently when no Income Tax Slab applies or computation fails."""
	if not int(_hr_setting("compute_tds_on_fnf", 0) or 0):
		return
	if not (doc.employee and doc.relieving_date):
		return

	try:
		tds = _compute_tds(doc)
	except Exception:
		frappe.log_error(
			title=f"TDS-on-FnF computation failed for {doc.name or '(new)'}",
			message=frappe.get_traceback(),
		)
		return

	doc.tds_on_final_settlement = flt(tds)
	if tds > 0:
		_upsert_component_line(doc, "receivables", TDS_COMPONENT, tds)
	else:
		_remove_component_line(doc, "receivables", TDS_COMPONENT)


def _compute_tds(doc):
	"""Returns the TDS amount to deduct on this FnF. Returns 0 when no
	slab applies."""
	from frappe.utils import get_fiscal_year

	fy = get_fiscal_year(doc.relieving_date, as_dict=True)
	if not fy:
		return 0

	# Sum YTD taxable from posted Salary Slips for this Employee × FY.
	ytd = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(gross_pay), 0), COALESCE(SUM(total_deduction), 0)
		FROM `tabSalary Slip`
		WHERE employee = %s AND docstatus = 1
		  AND start_date BETWEEN %s AND %s
		""",
		(doc.employee, fy.year_start_date, fy.year_end_date),
	)[0]
	ytd_gross = flt(ytd[0])

	# YTD TDS deducted via Salary Slip income_tax component.
	ytd_tds = flt(
		frappe.db.sql(
			"""
			SELECT COALESCE(SUM(sd.amount), 0)
			FROM `tabSalary Detail` sd
			JOIN `tabSalary Slip` ss ON ss.name = sd.parent
			WHERE ss.employee = %s AND ss.docstatus = 1
			  AND ss.start_date BETWEEN %s AND %s
			  AND sd.parentfield = 'deductions'
			  AND sd.salary_component IN ('Income Tax', 'TDS')
			""",
			(doc.employee, fy.year_start_date, fy.year_end_date),
		)[0][0]
	)

	# FnF gross payables (treat Gratuity, Leave Encashment as exempt for
	# simplicity — strictly speaking encashment is partially exempt up to
	# limit; HR can override via negotiated_waiver_amount if needed).
	fnf_taxable_payables = 0
	for row in doc.payables or []:
		if row.component in ("Gratuity", "Leave Encashment"):
			continue
		fnf_taxable_payables += flt(row.amount)

	projected_annual_taxable = ytd_gross + fnf_taxable_payables
	annual_tax = _apply_slab(projected_annual_taxable, doc.employee, doc.relieving_date)
	if annual_tax is None:
		return 0
	tds_on_fnf = annual_tax - ytd_tds
	return max(tds_on_fnf, 0)


def _apply_slab(annual_taxable, employee, on_date):
	"""Returns annual tax per applicable Income Tax Slab. None if no slab found."""
	# Try Employee's Payroll Period override first; else fall back to any
	# active slab on the relieving date.
	slab_name = frappe.db.get_value(
		"Income Tax Slab",
		{"disabled": 0, "effective_from": ("<=", on_date)},
		"name",
		order_by="effective_from desc",
	)
	if not slab_name:
		return None
	slab = frappe.get_doc("Income Tax Slab", slab_name)
	tax = 0
	for s in slab.slabs:
		from_amt = flt(s.from_amount)
		to_amt = flt(s.to_amount)
		pct = flt(s.percent_deduction) / 100.0
		if annual_taxable <= from_amt:
			break
		taxable_in_slab = min(annual_taxable, to_amt or annual_taxable) - from_amt
		if to_amt == 0:
			taxable_in_slab = annual_taxable - from_amt
		tax += max(taxable_in_slab, 0) * pct
		if to_amt and annual_taxable <= to_amt:
			break
	return tax


# ---- helpers for component-line upsert ----


def _has_component_line(doc, table, component):
	for row in doc.get(table) or []:
		if row.component == component:
			return True
	return False


def _has_component_line_with_ref(doc, table, component, ref_name):
	"""For Leave Encashment, ref_name is the leave_type (we identify the row
	by component+remark since reference_document may be empty before insert)."""
	for row in doc.get(table) or []:
		if row.component == component and (row.remark or "").endswith(ref_name):
			return True
		if row.component == component and row.reference_document == ref_name:
			return True
	return False


def _upsert_component_line(doc, table, component, amount, ref_type=None, ref_name=None):
	"""Insert or update a row with this component in the given table.
	If the row exists, refresh its amount + reference (rows are identified
	by component name uniquely for Phase 4-managed components)."""
	for row in doc.get(table) or []:
		if row.component == component:
			row.amount = flt(amount)
			if ref_type:
				row.reference_document_type = ref_type
			if ref_name:
				row.reference_document = ref_name
			row.status = "Settled" if flt(amount) == 0 else "Unsettled"
			return
	doc.append(
		table,
		{
			"component": component,
			"amount": flt(amount),
			"status": "Unsettled",
			"reference_document_type": ref_type,
			"reference_document": ref_name,
		},
	)


def _remove_component_line(doc, table, component):
	rows = doc.get(table) or []
	keep = [r for r in rows if r.component != component]
	if len(keep) != len(rows):
		doc.set(table, keep)


def _recompute_totals(doc):
	"""Mirror the core set_totals after we've mutated the tables."""
	total_payable = sum(flt(r.amount) for r in (doc.payables or []))
	total_receivable = sum(flt(r.amount) for r in (doc.receivables or []))
	doc.total_payable_amount = flt(total_payable, doc.precision("total_payable_amount"))
	doc.total_receivable_amount = flt(
		total_receivable + flt(doc.total_asset_recovery_cost or 0),
		doc.precision("total_receivable_amount"),
	)


# ---- Stage 6: Exit Letter generation ----

EXIT_LETTER_TYPES = ("Relieving Letter", "Experience Letter", "Service Certificate")


@frappe.whitelist()
def generate_exit_letters_from_fnf(fnf_name):
	"""Create three draft Appointment Letter records linked to this FnF,
	one per exit letter type, using the seeded templates.

	Idempotent — skips letter types that already have a draft for this FnF.
	Returns the list of letter names so the JS can offer Open links."""
	fnf = frappe.get_doc("Full and Final Statement", fnf_name)
	if not fnf.relieving_date:
		frappe.throw(_("Set Relieving Date on the FnF before generating exit letters."))
	if not fnf.employee:
		frappe.throw(_("FnF has no Employee."))

	employee_name = frappe.db.get_value("Employee", fnf.employee, "employee_name") or fnf.employee
	created = []
	for letter_type in EXIT_LETTER_TYPES:
		existing = frappe.db.exists(
			"Appointment Letter",
			{"full_and_final_statement": fnf.name, "letter_type": letter_type},
		)
		if existing:
			created.append(existing)
			continue

		template = frappe.db.get_value(
			"Appointment Letter Template", {"letter_type": letter_type}, "name"
		)
		if not template:
			frappe.msgprint(
				_("No template found for {0} — skipped. Create one to enable.").format(letter_type)
			)
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Appointment Letter",
				"job_applicant": "",  # exit letters bypass this — pattern from Probation Review
				"applicant_name": employee_name,
				"appointment_date": fnf.relieving_date,
				"company": fnf.company,
				"appointment_letter_template": template,
				"letter_type": letter_type,
				"employee": fnf.employee,
				"full_and_final_statement": fnf.name,
			}
		)
		try:
			doc.insert(ignore_permissions=True, ignore_mandatory=True)
			created.append(doc.name)
		except Exception:
			frappe.log_error(
				title=f"Exit letter generation failed: {letter_type} for {fnf.name}",
				message=frappe.get_traceback(),
			)

	if created:
		frappe.msgprint(
			_("Generated {0} exit letter draft(s). Edit content + finalise from the Appointment Letter list.").format(
				len(created)
			)
		)
	return created


def auto_generate_exit_letters_on_submit(doc, method=None):
	"""on_submit doc_event for Full and Final Statement — when the HR Setting
	auto_generate_exit_letters_on_fnf_submit is on, create the 3 exit letter
	drafts as a side effect of submitting the FnF."""
	if not int(_hr_setting("auto_generate_exit_letters_on_fnf_submit", 0) or 0):
		return
	try:
		generate_exit_letters_from_fnf(doc.name)
	except Exception:
		# Don't roll back the FnF submission for letter generation issues;
		# HR can click the manual button to retry.
		frappe.log_error(
			title=f"Auto exit letter generation failed for {doc.name}",
			message=frappe.get_traceback(),
		)
