# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Compliance Calendar engine — Phase 6C.

Three responsibilities:

1. AUTO-POPULATE Compliance Filing rows for a Company x FY from active
   Compliance Return Definitions. Period_start / period_end / due_date
   are derived per frequency + due_offset_from anchor.

2. AUTO-LINK existing filing docs (PF ECR / ESI / 24Q / PT / LWF /
   Form 16 / POSH Annual Report) back to their Compliance Filing row
   whenever they save — via doc_event handlers wired in hooks.py. When a
   filing flips to Generated / Filed we update the Compliance Filing's
   linked_filing_*, filed_on, filing_status (Filed or Late Filed), and
   penalty fields.

3. UNIFIED REMINDER scheduler — daily — that walks every Pending /
   In Progress Compliance Filing and notifies the right people at the
   right cadence (Upcoming / Due Today / Overdue / Escalation). Each
   reminder is logged to Compliance Filing Reminder Log; HR Digest
   summarises per Company.

Also exposes `seed_compliance_return_definitions(company)` — wired as
a Company on_update doc_event — that creates the 6 federal default CRD
rows on first save.

All HR Settings reads go through _hr_setting() so the file is safe to
ship before its companion patches run.
"""

from collections import defaultdict
from datetime import date as date_cls

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	add_months,
	add_years,
	flt,
	formatdate,
	get_first_day,
	get_last_day,
	getdate,
	now,
	nowdate,
	today,
)


HR_SETTINGS_DEFAULTS = {
	"compliance_calendar_upcoming_days": 7,
	"compliance_calendar_escalation_days_after_due": 3,
	"send_compliance_calendar_daily_digest": 1,
	"compliance_calendar_digest_recipients_role": "HR Manager",
	"auto_link_filings_to_calendar": 1,
}


# Maps Compliance Filing.return_type -> (filing doctype, period field
# name) on the underlying filing doctype. The period field is the
# canonical 'when was this filing for?' key used by
# _detect_existing_filing_for. Special values:
#   "fiscal_year"   -> Link Fiscal Year; we resolve year_start_date /
#                       year_end_date and match by fiscal_year name.
#   "fiscal_year+quarter" -> TDS Form 24Q quarterly: derive quarter
#                       string from the period.
#   "fiscal_year+halfyear" -> ESI Half Yearly: derive 'Apr-Sep' /
#                       'Oct-Mar' from period.
RETURN_TYPE_TO_FILING_DOCTYPE = {
	"PF ECR": ("PF ECR Filing", "wage_month"),
	"ESI Monthly": ("ESI Monthly Contribution", "wage_month"),
	"ESI Half-Yearly": ("ESI Half Yearly Return", "fiscal_year+halfyear"),
	"TDS Form 24Q": ("TDS Return Form 24Q", "fiscal_year+quarter"),
	"Professional Tax": ("Professional Tax Return", "period_start"),
	"LWF": ("LWF Return", "period_start"),
	"Form 16": ("Form 16", "fiscal_year"),
	"POSH Annual Report": ("POSH Annual Report", "fiscal_year"),
}

# Reverse: filing doctype -> return_type. Used by the doc_event.
FILING_DOCTYPE_TO_RETURN_TYPE = {v[0]: k for k, v in RETURN_TYPE_TO_FILING_DOCTYPE.items()}


# ---------------------------------------------------------------------------
# HR Settings safe helper
# ---------------------------------------------------------------------------


def _hr_setting(field, default=None):
	"""Returns default if the field doesn't exist (patches not yet run)."""
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
# Period generation helpers
# ---------------------------------------------------------------------------


def _months_between(start, end):
	"""Yield (month_start, month_end) for every month in [start, end]."""
	cur = get_first_day(start)
	end = getdate(end)
	while cur <= end:
		yield (cur, get_last_day(cur))
		cur = get_first_day(add_months(cur, 1))


def _quarters_for_fy(fy_start):
	"""TDS quarters by fiscal year (Apr-Mar) — Q1 Apr-Jun, Q2 Jul-Sep,
	Q3 Oct-Dec, Q4 Jan-Mar. Yields (label, start, end)."""
	fy_start = getdate(fy_start)
	fy_year = fy_start.year
	# fy_label e.g. "FY 2026-27"
	fy_label = f"FY {fy_year}-{str(fy_year + 1)[-2:]}"
	specs = [
		("Q1", date_cls(fy_year, 4, 1), date_cls(fy_year, 6, 30)),
		("Q2", date_cls(fy_year, 7, 1), date_cls(fy_year, 9, 30)),
		("Q3", date_cls(fy_year, 10, 1), date_cls(fy_year, 12, 31)),
		("Q4", date_cls(fy_year + 1, 1, 1), date_cls(fy_year + 1, 3, 31)),
	]
	for q, s, e in specs:
		yield (f"{q} {fy_label}", s, e)


def _half_years_for_fy(fy_start):
	"""ESI half-years: Apr-Sep (H1) and Oct-Mar (H2)."""
	fy_start = getdate(fy_start)
	fy_year = fy_start.year
	yield (
		f"Apr-Sep {fy_year}",
		date_cls(fy_year, 4, 1),
		date_cls(fy_year, 9, 30),
	)
	yield (
		f"Oct-Mar {fy_year}-{str(fy_year + 1)[-2:]}",
		date_cls(fy_year, 10, 1),
		date_cls(fy_year + 1, 3, 31),
	)


def _fy_window(fy_start):
	"""Returns (FY start, FY end, label) tuple for the FY anchored at fy_start."""
	fy_start = getdate(fy_start)
	fy_end = date_cls(fy_start.year + 1, 3, 31)
	label = f"FY {fy_start.year}-{str(fy_start.year + 1)[-2:]}"
	return (fy_start, fy_end, label)


def _due_date(period_start, period_end, definition):
	"""Apply due_offset_days from the configured anchor."""
	anchor = definition.due_offset_from or "Period End"
	if anchor == "Period End":
		base = getdate(period_end)
	elif anchor == "Period Start":
		base = getdate(period_start)
	elif anchor == "Fiscal Year End":
		# Indian FY ends 31 Mar of period_end's FY.
		pe = getdate(period_end)
		fy_year = pe.year if pe.month >= 4 else pe.year - 1
		base = date_cls(fy_year + 1, 3, 31)
	elif anchor == "Calendar Year End":
		base = date_cls(getdate(period_end).year, 12, 31)
	else:
		base = getdate(period_end)
	return add_days(base, int(definition.due_offset_days or 0))


def _half_year_due_date(period_end):
	"""ESI Half-Yearly statutory dues: 11 Nov (Apr-Sep) / 11 May (Oct-Mar).
	Overrides the generic offset for accuracy."""
	pe = getdate(period_end)
	if pe.month == 9:  # Apr-Sep
		return date_cls(pe.year, 11, 11)
	# Oct-Mar half closes 31 Mar -> due 11 May (same calendar year as period_end).
	return date_cls(pe.year, 5, 11)


# ---------------------------------------------------------------------------
# Auto-populate
# ---------------------------------------------------------------------------


def _spec_for_definition(definition, fy_start_date):
	"""Yield (period_label, period_start, period_end, due_date) for a given
	definition over the supplied FY window. fy_start_date is the FY's
	April 1."""
	frequency = (definition.frequency or "").strip()
	fy_start_d = getdate(fy_start_date)
	fy_end_d = date_cls(fy_start_d.year + 1, 3, 31)

	if frequency == "Monthly":
		for (ms, me) in _months_between(fy_start_d, fy_end_d):
			label = ms.strftime("%b %Y")
			yield (label, ms, me, _due_date(ms, me, definition))

	elif frequency == "Quarterly":
		for label, qs, qe in _quarters_for_fy(fy_start_d):
			yield (label, qs, qe, _due_date(qs, qe, definition))

	elif frequency == "Half-yearly":
		for label, hs, he in _half_years_for_fy(fy_start_d):
			# ESI override
			if definition.return_type == "ESI Half-Yearly":
				due = _half_year_due_date(he)
			else:
				due = _due_date(hs, he, definition)
			yield (label, hs, he, due)

	elif frequency == "Annual":
		s, e, label = _fy_window(fy_start_d)
		yield (label, s, e, _due_date(s, e, definition))

	elif frequency == "One-time":
		# One-time: spawn a single row with the FY as the period.
		s, e, label = _fy_window(fy_start_d)
		yield (label, s, e, _due_date(s, e, definition))


def _get_fy_start_for(from_date):
	"""Returns the April 1 of the FY containing from_date."""
	d = getdate(from_date)
	year = d.year if d.month >= 4 else d.year - 1
	return date_cls(year, 4, 1)


def _existing_compliance_filing_name(company, return_type, state, period_start, period_end):
	filters = {
		"company": company,
		"return_type": return_type,
		"period_start": period_start,
		"period_end": period_end,
	}
	if state:
		filters["state"] = state
	return frappe.db.exists("Compliance Filing", filters)


def _detect_existing_filing_for(return_type, company, state, period_start, period_end):
	"""Find a pre-existing underlying filing doc (PF ECR / ESI / ...) that
	covers this exact period. Returns (doctype, name) or (None, None)."""
	spec = RETURN_TYPE_TO_FILING_DOCTYPE.get(return_type)
	if not spec:
		return (None, None)
	dt, period_field = spec

	if not frappe.db.exists("DocType", dt):
		return (None, None)

	# Resolve FY (used by fiscal_year-keyed filings).
	def _resolve_fy_name():
		return frappe.db.get_value(
			"Fiscal Year",
			{"year_start_date": ("<=", period_start), "year_end_date": (">=", period_end)},
			"name",
		)

	if period_field == "fiscal_year":
		fy_meta = _resolve_fy_name()
		if not fy_meta:
			return (None, None)
		hits = frappe.get_all(
			dt,
			filters={"company": company, "fiscal_year": fy_meta},
			fields=["name", "docstatus"],
			limit=1,
		)
	elif period_field == "fiscal_year+quarter":
		fy_meta = _resolve_fy_name()
		if not fy_meta:
			return (None, None)
		# Derive quarter from period_start month: Apr=Q1 Jul=Q2 Oct=Q3 Jan=Q4
		ps = getdate(period_start)
		q_map = {4: "Q1", 7: "Q2", 10: "Q3", 1: "Q4"}
		q = q_map.get(ps.month)
		if not q:
			return (None, None)
		hits = frappe.get_all(
			dt,
			filters={"company": company, "fiscal_year": fy_meta, "quarter": q},
			fields=["name", "docstatus"],
			limit=1,
		)
	elif period_field == "fiscal_year+halfyear":
		fy_meta = _resolve_fy_name()
		if not fy_meta:
			return (None, None)
		ps = getdate(period_start)
		hy = "Apr-Sep" if ps.month == 4 else ("Oct-Mar" if ps.month == 10 else None)
		if not hy:
			return (None, None)
		hits = frappe.get_all(
			dt,
			filters={"company": company, "fiscal_year": fy_meta, "period": hy},
			fields=["name", "docstatus"],
			limit=1,
		)
	else:
		# Try matching by period_start (most filings store first-of-month or
		# first-of-period). PF ECR uses wage_month which is the first day of
		# the wage month -> matches period_start.
		filters = {"company": company, period_field: period_start}
		if state and frappe.get_meta(dt).get_field("state"):
			filters["state"] = state
		hits = frappe.get_all(
			dt, filters=filters, fields=["name", "docstatus"], limit=1
		)
	if hits:
		return (dt, hits[0].name)
	return (None, None)


def _filing_status_for_underlying(dt, name):
	"""Map underlying doctype's filing status to Compliance Filing status."""
	if not (dt and name):
		return "Pending"
	# Most Phase 6B doctypes have a 'filing_status' field with Draft /
	# Generated / Filed / Cancelled.
	meta = frappe.get_meta(dt)
	if meta.get_field("filing_status"):
		val = frappe.db.get_value(dt, name, "filing_status")
		if val == "Filed":
			return "Filed"
		if val in ("Draft", "Generated"):
			return "In Progress"
		if val == "Cancelled":
			return "Pending"
	# Form 16 uses docstatus.
	if dt == "Form 16":
		docstatus = frappe.db.get_value(dt, name, "docstatus")
		if docstatus == 1:
			return "Filed"
		return "In Progress"
	# POSH Annual Report uses status (Draft / Submitted) field.
	if dt == "POSH Annual Report":
		docstatus = frappe.db.get_value(dt, name, "docstatus")
		if docstatus == 1:
			return "Filed"
		return "In Progress"
	return "In Progress"


def _filed_on_for_underlying(dt, name):
	if not (dt and name):
		return None
	meta = frappe.get_meta(dt)
	if meta.get_field("filed_on"):
		return frappe.db.get_value(dt, name, "filed_on")
	# Form 16 — use modified date.
	return None


@frappe.whitelist()
def populate_compliance_filings_for_period(company, from_date, to_date):
	"""Generate Compliance Filing rows for every Compliance Return Definition
	belonging to `company` that's active in [from_date, to_date].

	Idempotent: skips periods that already have a row. Returns counts."""
	from_d = getdate(from_date)
	to_d = getdate(to_date)
	if to_d < from_d:
		frappe.throw(_("to_date must be >= from_date."))

	created = []
	updated = []
	skipped_existing = 0

	# Build list of FY starts that overlap [from_d, to_d]; usually 1 or 2.
	fy_starts = set()
	cursor = from_d
	while cursor <= to_d:
		fy_starts.add(_get_fy_start_for(cursor))
		cursor = add_months(cursor, 1)

	definitions = frappe.get_all(
		"Compliance Return Definition",
		filters={"company": company, "applicable": 1},
		fields=[
			"name",
			"company",
			"return_type",
			"state",
			"frequency",
			"due_offset_days",
			"due_offset_from",
			"responsible_person",
			"linked_filing_doctype",
			"effective_from",
			"effective_to",
		],
	)

	for d in definitions:
		# Effective_from / effective_to bounds.
		ef = getdate(d.effective_from) if d.effective_from else None
		et = getdate(d.effective_to) if d.effective_to else None

		# Wrap dict as a simple namespace for _spec_for_definition.
		def _attr(k):
			return d.get(k)

		class _Def:
			pass

		ddef = _Def()
		ddef.frequency = d.frequency
		ddef.return_type = d.return_type
		ddef.due_offset_days = d.due_offset_days
		ddef.due_offset_from = d.due_offset_from

		for fy_start in sorted(fy_starts):
			for label, ps, pe, due in _spec_for_definition(ddef, fy_start):
				# Clip to (from_d, to_d) window: include if period overlaps.
				if pe < from_d or ps > to_d:
					continue
				if ef and pe < ef:
					continue
				if et and ps > et:
					continue

				existing_cf = _existing_compliance_filing_name(
					d.company, d.return_type, d.state, ps, pe
				)
				if existing_cf:
					skipped_existing += 1
					# Refresh linked filing if missing.
					_maybe_relink(existing_cf, d, ps, pe)
					continue

				# Create.
				dt, dname = _detect_existing_filing_for(d.return_type, d.company, d.state, ps, pe)
				doc_dict = {
					"doctype": "Compliance Filing",
					"company": d.company,
					"return_type": d.return_type,
					"state": d.state or None,
					"period_label": label,
					"period_start": ps,
					"period_end": pe,
					"due_date": due,
					"filing_status": _filing_status_for_underlying(dt, dname) if dt else "Pending",
					"linked_filing_doctype": dt,
					"linked_filing_name": dname,
					"filed_on": _filed_on_for_underlying(dt, dname),
					"responsible_person": d.responsible_person,
				}
				try:
					cf = frappe.get_doc(doc_dict).insert(ignore_permissions=True)
					created.append(cf.name)
					# If linked and Filed and past due, compute penalty.
					if dt and cf.filing_status == "Filed" and cf.filed_on and cf.due_date:
						if getdate(cf.filed_on) > getdate(cf.due_date):
							cf.filing_status = "Late Filed"
							cf.days_late = (getdate(cf.filed_on) - getdate(cf.due_date)).days
							amount, basis = _compute_penalty(cf, definition=d)
							cf.penalty_amount = amount
							cf.penalty_basis = basis
							cf.save(ignore_permissions=True)
				except frappe.DuplicateEntryError:
					skipped_existing += 1
				except Exception:
					frappe.log_error(
						title=f"Compliance Filing create failed: {d.return_type}/{label}",
						message=frappe.get_traceback(),
					)

	return {
		"created_count": len(created),
		"updated_count": len(updated),
		"skipped_existing": skipped_existing,
		"created": created[:50],
	}


def _maybe_relink(compliance_filing_name, definition, period_start, period_end):
	"""If a Compliance Filing exists but has no linked filing, try to
	back-link if we now detect an underlying doc."""
	cf = frappe.db.get_value(
		"Compliance Filing",
		compliance_filing_name,
		["linked_filing_doctype", "linked_filing_name", "filing_status"],
		as_dict=True,
	)
	if cf and cf.linked_filing_doctype and cf.linked_filing_name:
		return
	dt, dname = _detect_existing_filing_for(
		definition.return_type, definition.company, definition.state, period_start, period_end
	)
	if dt and dname:
		frappe.db.set_value(
			"Compliance Filing",
			compliance_filing_name,
			{
				"linked_filing_doctype": dt,
				"linked_filing_name": dname,
				"filing_status": _filing_status_for_underlying(dt, dname),
				"filed_on": _filed_on_for_underlying(dt, dname),
			},
			update_modified=False,
		)


@frappe.whitelist()
def auto_populate_current_year(company):
	"""Auto-populate Compliance Filings for the current FY (April -> March)."""
	td = getdate(today())
	fy_start = _get_fy_start_for(td)
	fy_end = date_cls(fy_start.year + 1, 3, 31)
	return populate_compliance_filings_for_period(company, fy_start, fy_end)


# ---------------------------------------------------------------------------
# Auto-link on save (doc_event for each filing doctype)
# ---------------------------------------------------------------------------


def auto_link_filing_on_save(doc, method=None):
	"""doc_event: when a filing doctype saves, find its Compliance Filing
	row (Company x Return Type x matching period) and back-link.

	HR Settings-gated by auto_link_filings_to_calendar (default on)."""
	if not int(_hr_setting("auto_link_filings_to_calendar", 1) or 0):
		return

	return_type = FILING_DOCTYPE_TO_RETURN_TYPE.get(doc.doctype)
	if not return_type:
		return

	# Resolve the matching period.
	period_start = None
	period_end = None

	if doc.doctype == "PF ECR Filing":
		# wage_month is first-of-month.
		if not doc.wage_month:
			return
		period_start = get_first_day(doc.wage_month)
		period_end = get_last_day(period_start)
	elif doc.doctype == "ESI Monthly Contribution":
		# wage_month is first-of-month (matches PF ECR convention).
		field = doc.get("wage_month") or doc.get("period_start")
		if not field:
			return
		period_start = get_first_day(field)
		period_end = get_last_day(period_start)
	elif doc.doctype == "TDS Return Form 24Q":
		# fiscal_year + quarter -> derive period_start / period_end.
		fy = doc.get("fiscal_year")
		q = doc.get("quarter")
		if not (fy and q):
			return
		fy_row = frappe.db.get_value(
			"Fiscal Year", fy, ["year_start_date", "year_end_date"], as_dict=True
		)
		if not fy_row:
			return
		fy_year = fy_row.year_start_date.year
		q_map = {
			"Q1": (date_cls(fy_year, 4, 1), date_cls(fy_year, 6, 30)),
			"Q2": (date_cls(fy_year, 7, 1), date_cls(fy_year, 9, 30)),
			"Q3": (date_cls(fy_year, 10, 1), date_cls(fy_year, 12, 31)),
			"Q4": (date_cls(fy_year + 1, 1, 1), date_cls(fy_year + 1, 3, 31)),
		}
		if q not in q_map:
			return
		period_start, period_end = q_map[q]
	elif doc.doctype == "ESI Half Yearly Return":
		fy = doc.get("fiscal_year")
		period = doc.get("period")
		if not (fy and period):
			return
		fy_row = frappe.db.get_value(
			"Fiscal Year", fy, ["year_start_date", "year_end_date"], as_dict=True
		)
		if not fy_row:
			return
		fy_year = fy_row.year_start_date.year
		if period == "Apr-Sep":
			period_start = date_cls(fy_year, 4, 1)
			period_end = date_cls(fy_year, 9, 30)
		else:  # Oct-Mar
			period_start = date_cls(fy_year, 10, 1)
			period_end = date_cls(fy_year + 1, 3, 31)
	elif doc.doctype in ("Professional Tax Return", "LWF Return"):
		if not (doc.get("period_start") and doc.get("period_end")):
			return
		period_start = getdate(doc.period_start)
		period_end = getdate(doc.period_end)
	elif doc.doctype == "Form 16":
		# fiscal_year -> resolve to start/end.
		fy = doc.get("fiscal_year")
		if not fy:
			return
		fy_row = frappe.db.get_value(
			"Fiscal Year", fy, ["year_start_date", "year_end_date"], as_dict=True
		)
		if not fy_row:
			return
		period_start = fy_row.year_start_date
		period_end = fy_row.year_end_date
	elif doc.doctype == "POSH Annual Report":
		# fiscal_year (Link to Fiscal Year)
		fy = doc.get("fiscal_year")
		if not fy:
			return
		fy_row = frappe.db.get_value(
			"Fiscal Year", fy, ["year_start_date", "year_end_date"], as_dict=True
		)
		if not fy_row:
			return
		period_start = fy_row.year_start_date
		period_end = fy_row.year_end_date

	if not (period_start and period_end):
		return

	state = doc.get("state") if frappe.get_meta(doc.doctype).get_field("state") else None

	# Find matching Compliance Filing.
	filters = {
		"company": doc.company,
		"return_type": return_type,
		"period_start": period_start,
		"period_end": period_end,
	}
	if state:
		filters["state"] = state

	cf_name = frappe.db.exists("Compliance Filing", filters)
	if not cf_name:
		# Try a looser match — period contains period_start (helpful when the
		# CF was generated with slightly different period_end like '30' vs
		# '31' due to month length quirks).
		looser = frappe.db.exists(
			"Compliance Filing",
			{
				"company": doc.company,
				"return_type": return_type,
				"period_start": period_start,
			},
		)
		cf_name = looser

	if not cf_name:
		return

	cf = frappe.get_doc("Compliance Filing", cf_name)
	cf.linked_filing_doctype = doc.doctype
	cf.linked_filing_name = doc.name

	new_status = _filing_status_for_underlying(doc.doctype, doc.name)
	# Don't clobber Waived / Not Applicable.
	if cf.filing_status not in ("Waived", "Not Applicable"):
		filed_on = _filed_on_for_underlying(doc.doctype, doc.name)
		if filed_on:
			cf.filed_on = filed_on
		# Capture amount_filed FIRST so penalty calc has the correct base.
		amt_field = (
			"challan_amount"
			if frappe.get_meta(doc.doctype).get_field("challan_amount")
			else None
		)
		if amt_field:
			amt = doc.get(amt_field)
			if amt:
				cf.amount_filed = amt
		if new_status == "Filed":
			# Check if late.
			if cf.filed_on and cf.due_date and getdate(cf.filed_on) > getdate(cf.due_date):
				cf.filing_status = "Late Filed"
				cf.days_late = (getdate(cf.filed_on) - getdate(cf.due_date)).days
				amount, basis = _compute_penalty(cf)
				cf.penalty_amount = amount
				cf.penalty_basis = basis
			else:
				cf.filing_status = "Filed"
				cf.days_late = 0
				cf.penalty_amount = 0
				cf.penalty_basis = ""
		else:
			cf.filing_status = new_status

	try:
		cf.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title=f"auto_link_filing_on_save failed for {doc.doctype}/{doc.name}",
			message=frappe.get_traceback(),
		)


# ---------------------------------------------------------------------------
# Penalty computation
# ---------------------------------------------------------------------------


def _compute_penalty(compliance_filing, definition=None):
	"""Returns (amount, basis_description). Reads the CRD if not supplied.

	Defaults applied when the CRD is missing or unconfigured:
	  PF ECR / ESI: 12% p.a. on amount_filed
	  TDS 24Q: Rs 200/day capped at amount_filed
	  PT / LWF: penalty_rate_pct from CRD (default 0)
	"""
	cf = compliance_filing
	days = int(cf.days_late or 0)
	if days <= 0:
		return (0, "")

	# Find CRD if not passed.
	if not definition:
		filters = {
			"company": cf.company,
			"return_type": cf.return_type,
			"applicable": 1,
		}
		if cf.state:
			filters["state"] = cf.state
		crd_name = frappe.db.exists("Compliance Return Definition", filters)
		definition = frappe.get_doc("Compliance Return Definition", crd_name) if crd_name else None

	rate_pa = flt(definition.penalty_rate_pct) if definition else 0
	per_day = flt(definition.penalty_per_day) if definition else 0
	basis_desc = (definition.penalty_basis_description if definition else "") or ""

	amount = 0
	basis = ""

	if cf.return_type in ("PF ECR", "ESI Monthly", "ESI Half-Yearly"):
		# Interest on amount_filed at penalty_rate_pct p.a. (default 12).
		eff_rate = rate_pa or 12.0
		base = flt(cf.amount_filed)
		amount = round(base * (eff_rate / 100.0) * (days / 365.0), 2)
		basis = f"{cf.return_type}: {eff_rate}% p.a. interest on Rs {int(base):,} for {days} day(s)."
	elif cf.return_type == "TDS Form 24Q":
		fee_per_day = per_day or 200
		raw = flt(fee_per_day) * days
		cap = flt(cf.amount_filed)
		amount = min(raw, cap) if cap else raw
		basis = f"S.234E: Rs {int(fee_per_day)}/day x {days} day(s) = Rs {int(raw):,} (capped at TDS amount Rs {int(cap):,})."
	elif cf.return_type in ("Professional Tax", "LWF"):
		eff_rate = rate_pa or 0
		base = flt(cf.amount_filed)
		amount = round(base * (eff_rate / 100.0) * (days / 365.0), 2) if eff_rate else 0
		basis = (
			f"{cf.return_type}: {eff_rate}% p.a. on Rs {int(base):,} for {days} day(s)."
			if eff_rate
			else "State-specific — configure penalty_rate_pct on the CRD."
		)
	elif cf.return_type == "POSH Annual Report":
		# Sec 26 — up to Rs 50,000. Use flat default.
		amount = 50000
		basis = "POSH Sec 26: penalty up to Rs 50,000 for non-filing."
	else:
		if basis_desc:
			basis = basis_desc
		else:
			basis = f"No automatic penalty rule for {cf.return_type}; configure CRD."

	return (amount, basis)


# ---------------------------------------------------------------------------
# Seed defaults on Company creation
# ---------------------------------------------------------------------------


# Federal-default Compliance Return Definitions seeded on Company.on_update.
# State-specific (PT / LWF / S&E) are NOT auto-seeded — HR adds per their
# state registrations.
SEED_DEFINITIONS = [
	{
		"return_type": "PF ECR",
		"frequency": "Monthly",
		"due_offset_days": 15,
		"due_offset_from": "Period End",
		"linked_filing_doctype": "PF ECR Filing",
		"penalty_rate_pct": 12,
		"penalty_basis_description": "EPFO: 12% p.a. interest on outstanding + 5-25% damages based on delay.",
	},
	{
		"return_type": "ESI Monthly",
		"frequency": "Monthly",
		"due_offset_days": 15,
		"due_offset_from": "Period End",
		"linked_filing_doctype": "ESI Monthly Contribution",
		"penalty_rate_pct": 12,
		"penalty_basis_description": "ESIC: 12% p.a. interest + damages similar to EPFO.",
	},
	{
		"return_type": "ESI Half-Yearly",
		"frequency": "Half-yearly",
		"due_offset_days": 42,  # Sept 30 + 42 = Nov 11; Mar 31 + 41 = May 11. Half-year handler overrides.
		"due_offset_from": "Period End",
		"linked_filing_doctype": "ESI Half Yearly Return",
		"penalty_rate_pct": 12,
	},
	{
		"return_type": "TDS Form 24Q",
		"frequency": "Quarterly",
		"due_offset_days": 31,
		"due_offset_from": "Period End",
		"linked_filing_doctype": "TDS Return Form 24Q",
		"penalty_per_day": 200,
		"penalty_basis_description": "S.234E: Rs 200/day late filing fee, capped at TDS amount.",
	},
	{
		"return_type": "Form 16",
		"frequency": "Annual",
		"due_offset_days": 76,  # 31 Mar (FY end) + 76 days = 15 Jun
		"due_offset_from": "Period End",
		"linked_filing_doctype": "Form 16",
	},
	{
		"return_type": "POSH Annual Report",
		"frequency": "Annual",
		"due_offset_days": 0,  # 31 Mar / 31 Dec per IC discretion
		"due_offset_from": "Calendar Year End",
		"linked_filing_doctype": "POSH Annual Report",
		"penalty_basis_description": "POSH Sec 26: up to Rs 50,000.",
	},
]


def seed_compliance_return_definitions(doc=None, method=None, company_name=None):
	"""Company on_update: seed the 6 federal-default Compliance Return
	Definitions if none exist for this Company.

	Idempotent. Can be called from a patch passing company_name explicitly."""
	company = company_name or (doc.name if doc else None)
	if not company:
		return

	# Skip if HR Settings has not yet been migrated to include the feature
	# (graceful before-patch behavior).
	if not frappe.db.exists("DocType", "Compliance Return Definition"):
		return

	# Skip if any CRD already exists for the Company.
	existing = frappe.db.count("Compliance Return Definition", {"company": company})
	if existing:
		return

	# Anchor effective_from to the start of the current Indian FY so newly-
	# created Companies pick up the full FY (Apr -> Mar) when HR clicks
	# 'auto-populate', not just the months remaining after today.
	td = getdate(today())
	fy_anchor_year = td.year if td.month >= 4 else td.year - 1
	fy_anchor = date_cls(fy_anchor_year, 4, 1)

	for spec in SEED_DEFINITIONS:
		try:
			frappe.get_doc(
				{
					"doctype": "Compliance Return Definition",
					"company": company,
					"applicable": 1,
					"effective_from": fy_anchor,
					**spec,
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"Compliance Return Definition seed failed: {company}/{spec.get('return_type')}",
				message=frappe.get_traceback(),
			)


# ---------------------------------------------------------------------------
# Unified daily reminder scheduler
# ---------------------------------------------------------------------------


def send_compliance_calendar_reminders():
	"""Daily scheduler. Walks every Pending / In Progress Compliance Filing:

	  - due in <= upcoming_days days -> Upcoming (PWA + ToDo to responsible)
	  - due today -> Due Today (PWA + email)
	  - past due -> Overdue (PWA + email; escalate to HR Manager if past
	    due + escalation_days)

	Stamps last_reminder_sent_on (date-based, NULL-safe).
	Logs each reminder to Compliance Filing Reminder Log.
	HR digest summarises per Company.
	"""
	upcoming_days = int(_hr_setting("compliance_calendar_upcoming_days", 7) or 7)
	escalation_days = int(_hr_setting("compliance_calendar_escalation_days_after_due", 3) or 3)

	td = getdate(today())
	cutoff = add_days(td, upcoming_days)

	# Use raw SQL for NULL-safe filtering on last_reminder_sent_on.
	rows = frappe.db.sql(
		"""
		SELECT name, company, return_type, period_label, due_date,
		       filing_status, responsible_person, escalated, state,
		       last_reminder_sent_on
		  FROM `tabCompliance Filing`
		 WHERE filing_status IN ('Pending', 'In Progress')
		   AND due_date <= %s
		   AND (last_reminder_sent_on IS NULL OR last_reminder_sent_on != %s)
		""",
		(cutoff, td),
		as_dict=True,
	)
	if not rows:
		return

	digest_per_company = defaultdict(list)
	for r in rows:
		due = getdate(r.due_date)
		if due < td:
			reminder_type = "Overdue"
		elif due == td:
			reminder_type = "Due Today"
		else:
			reminder_type = "Upcoming"

		_notify_compliance_filing(r, reminder_type)
		digest_per_company[r.company].append({**dict(r), "reminder_type": reminder_type})

		# Escalation: past due + escalation_days, not yet escalated.
		if reminder_type == "Overdue" and (td - due).days >= escalation_days and not int(
			r.escalated or 0
		):
			_escalate_compliance_filing(r)

		# Stamp last_reminder_sent_on.
		frappe.db.set_value(
			"Compliance Filing",
			r.name,
			"last_reminder_sent_on",
			td,
			update_modified=False,
		)

	# HR digest.
	if int(_hr_setting("send_compliance_calendar_daily_digest", 1) or 0):
		_send_hr_compliance_digest(digest_per_company, td)


def _notify_compliance_filing(row, reminder_type):
	"""Per-Compliance-Filing notifications: PWA + ToDo or email per type."""
	user = row.responsible_person
	channels_attempted = []
	if user and user not in ("Administrator", "Guest"):
		# PWA notification.
		ok = _safe_pwa_notification(
			to_user=user,
			message=f"[{reminder_type}] {row.return_type} ({row.period_label}) for {row.company} — due {formatdate(row.due_date)}.",
			ref_type="Compliance Filing",
			ref_name=row.name,
		)
		channels_attempted.append(("PWA Notification", user, ok))

		if reminder_type in ("Due Today", "Overdue"):
			# Email
			try:
				frappe.sendmail(
					recipients=[user],
					subject=f"[Compliance] {reminder_type}: {row.return_type} for {row.company}",
					message=(
						f"<p>{row.return_type} filing for <b>{row.company}</b> "
						f"({row.period_label}) is <b>{reminder_type}</b>.</p>"
						f"<p>Due: {formatdate(row.due_date)}<br>"
						f"<a href='/app/compliance-filing/{row.name}'>Open Compliance Filing</a></p>"
					),
					now=False,
				)
				channels_attempted.append(("Email", user, True))
			except Exception:
				channels_attempted.append(("Email", user, False))
				frappe.log_error(
					title=f"Compliance email failed: {row.name}/{user}",
					message=frappe.get_traceback(),
				)

		if reminder_type == "Upcoming":
			# ToDo (only Upcoming -> avoid duplicates; Due Today already in email).
			_upsert_compliance_todo(row, user)
			channels_attempted.append(("ToDo", user, True))

	# Always log each attempt, even when there's no responsible person — so
	# HR can see we tried.
	if not channels_attempted:
		_log_reminder(row.name, reminder_type, "PWA Notification", "(unassigned)", "No responsible_person set.")
	else:
		for ch, recipient, ok in channels_attempted:
			_log_reminder(
				row.name,
				reminder_type,
				ch,
				recipient,
				"OK" if ok else "FAILED",
			)


def _upsert_compliance_todo(row, user):
	existing = frappe.db.exists(
		"ToDo",
		{
			"reference_type": "Compliance Filing",
			"reference_name": row.name,
			"allocated_to": user,
			"status": "Open",
		},
	)
	if existing:
		return
	try:
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": user,
				"reference_type": "Compliance Filing",
				"reference_name": row.name,
				"description": (
					f"Upcoming compliance filing: {row.return_type} for {row.company} "
					f"({row.period_label}) due {formatdate(row.due_date)}."
				),
				"date": row.due_date,
				"priority": "High",
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title=f"Compliance ToDo failed: {row.name}/{user}",
			message=frappe.get_traceback(),
		)


def _escalate_compliance_filing(row):
	"""Escalation -> notify all HR Manager role holders + flag escalated=1."""
	role = _hr_setting("compliance_calendar_digest_recipients_role", "HR Manager") or "HR Manager"
	hr_users = frappe.get_all(
		"Has Role",
		filters={"role": role, "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	hr_users = [u for u in hr_users if u and u not in ("Administrator", "Guest")]
	for u in hr_users:
		_safe_pwa_notification(
			to_user=u,
			message=(
				f"[Escalation] {row.return_type} for {row.company} ({row.period_label}) "
				f"is overdue (was due {formatdate(row.due_date)})."
			),
			ref_type="Compliance Filing",
			ref_name=row.name,
		)
		_log_reminder(row.name, "Escalation", "PWA Notification", u, "Escalated to HR Manager.")
	frappe.db.set_value("Compliance Filing", row.name, "escalated", 1, update_modified=False)


def _send_hr_compliance_digest(per_company, today_d):
	role = _hr_setting("compliance_calendar_digest_recipients_role", "HR Manager") or "HR Manager"
	hr_users = frappe.get_all(
		"Has Role",
		filters={"role": role, "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	hr_users = [u for u in hr_users if u and u not in ("Administrator", "Guest")]
	if not hr_users:
		return

	sections = []
	for company, items in per_company.items():
		sections.append(
			f"<h4 style='margin-top:16px'>{frappe.utils.escape_html(company or '(no company)')}</h4>"
		)
		sections.append(
			"<table border='1' cellpadding='6' cellspacing='0' "
			"style='border-collapse:collapse;font-size:13px'>"
			"<tr><th>Return</th><th>Period</th><th>Due</th><th>Status</th>"
			"<th>Reminder</th></tr>"
		)
		for it in sorted(items, key=lambda a: a["due_date"]):
			color = (
				"#c0392b"
				if it["reminder_type"] == "Overdue"
				else ("#e67e22" if it["reminder_type"] == "Due Today" else "#2980b9")
			)
			sections.append(
				"<tr>"
				f"<td>{frappe.utils.escape_html(it['return_type'])}</td>"
				f"<td>{frappe.utils.escape_html(it['period_label'] or '')}</td>"
				f"<td>{formatdate(it['due_date'])}</td>"
				f"<td>{frappe.utils.escape_html(it['filing_status'])}</td>"
				f"<td style='color:{color}'><strong>{it['reminder_type']}</strong></td>"
				"</tr>"
			)
		sections.append("</table>")

	body = (
		f"<p>Compliance Calendar digest for {today_d}. "
		f"{sum(len(v) for v in per_company.values())} filing(s) need attention across "
		f"{len(per_company)} company(ies).</p>"
		+ "".join(sections)
		+ "<p style='margin-top:16px;font-size:12px;color:#777'>"
		"Daily compliance digest from indian_hrms_compliance.</p>"
	)
	try:
		frappe.sendmail(
			recipients=hr_users,
			subject=f"[HRMS] Compliance Calendar Digest — {today_d}",
			message=body,
			now=False,
		)
	except Exception:
		frappe.log_error(
			title="Compliance digest email failed",
			message=frappe.get_traceback(),
		)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_pwa_notification(to_user, message, ref_type, ref_name):
	if not frappe.db.exists("DocType", "PWA Notification"):
		return False
	try:
		frappe.get_doc(
			{
				"doctype": "PWA Notification",
				"to_user": to_user,
				"from_user": frappe.session.user or "Administrator",
				"message": message,
				"reference_document_type": ref_type,
				"reference_document_name": ref_name,
				"category": "Compliance",
			}
		).insert(ignore_permissions=True)
		return True
	except Exception:
		frappe.log_error(title="Compliance PWA notification failed", message=frappe.get_traceback())
		return False


def _log_reminder(compliance_filing, reminder_type, channel, recipient, message):
	try:
		frappe.get_doc(
			{
				"doctype": "Compliance Filing Reminder Log",
				"compliance_filing": compliance_filing,
				"sent_on": now(),
				"reminder_type": reminder_type,
				"channel": channel,
				"recipient": recipient,
				"message": message,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title=f"Compliance Reminder Log insert failed: {compliance_filing}",
			message=frappe.get_traceback(),
		)
