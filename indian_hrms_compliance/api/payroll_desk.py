# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Payroll Control Center — one aggregated payload + actions for the unified
Payroll Desk page. Packages readiness, KPIs, compliance deadlines, a no-commit
run preview, and a guided monthly payroll run over the existing Payroll Entry.

HR-only and company-scoped (Administrator / no-Employee user may pass company).
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_first_day, get_last_day, getdate, nowdate

PAYROLL_ROLES = ("HR Manager", "HR User", "System Manager")
FILED_STATUSES = ("Filed", "Late Filed", "Waived", "Not Applicable")
DUE_SOON_DAYS = 45


def _guard():
	frappe.only_for(PAYROLL_ROLES)


def _resolve_company(company=None):
	if company:
		return company
	from indian_hrms_compliance.api.cockpit import _scope_company

	return _scope_company() or frappe.db.get_value("Company", {}, "name")


# --------------------------------------------------------------------- overview
@frappe.whitelist()
def get_payroll_overview(company=None):
	_guard()
	company = _resolve_company(company)
	today = getdate(nowdate())

	return {
		"company": company,
		"as_of": str(today),
		"kpis": _kpis(company, today),
		"readiness": _readiness(company, today),
		"employee_readiness": _employee_readiness(company),
		"compliance": _compliance(company, today),
		"recent_runs": _recent_runs(company),
		"suggested_period": _suggested_period(company, today),
	}


def _kpis(company, today):
	active = frappe.db.count("Employee", {"company": company, "status": "Active"})
	on_ssa = len(
		set(frappe.get_all("Salary Structure Assignment", {"docstatus": 1, "company": company}, pluck="employee"))
	)
	month_start, month_end = get_first_day(today), get_last_day(today)
	slips_month = frappe.db.count(
		"Salary Slip", {"company": company, "start_date": (">=", month_start), "start_date": ("<=", month_end)}
	)
	draft_slips = frappe.db.count(
		"Salary Slip",
		{"company": company, "docstatus": 0, "start_date": (">=", month_start), "start_date": ("<=", month_end)},
	)
	return [
		{"key": "active", "label": "Active Employees", "value": active, "tone": "brand"},
		{"key": "on_payroll", "label": "On Payroll (assigned)", "value": on_ssa, "tone": "green"},
		{"key": "slips_month", "label": "Slips This Month", "value": slips_month, "tone": "violet"},
		{"key": "draft_slips", "label": "Draft Slips", "value": draft_slips, "tone": "amber" if draft_slips else "grey"},
	]


def _readiness(company, today):
	"""Each item: {key, label, ok, detail, route} — ok=False blocks/【warns a run."""
	from indian_hrms_compliance.payroll.doctype.payroll_period.payroll_period import get_payroll_period

	items = []

	active = frappe.db.count("Employee", {"company": company, "status": "Active"})
	items.append({
		"key": "employees", "label": _("Active employees exist"), "ok": active > 0,
		"detail": _("{0} active").format(active), "route": "/app/employee",
	})

	slab = frappe.db.exists("Income Tax Slab", {"docstatus": 1, "disabled": 0, "company": company}) or frappe.db.exists(
		"Income Tax Slab", {"docstatus": 1, "disabled": 0, "company": ("in", ("", None))}
	)
	items.append({
		"key": "tax_slab", "label": _("Income Tax Slab available"), "ok": bool(slab),
		"detail": _("Found") if slab else _("Create a national or company slab"), "route": "/app/income-tax-slab",
	})

	pp = get_payroll_period(today, today, company)
	items.append({
		"key": "payroll_period", "label": _("Payroll Period covers today"), "ok": bool(pp),
		"detail": pp.name if pp else _("None — auto-created from Fiscal Year"), "route": "/app/payroll-period",
	})

	structures = frappe.db.count("Salary Structure", {"company": company, "docstatus": 1, "is_active": "Yes"})
	items.append({
		"key": "structures", "label": _("Active Salary Structures"), "ok": structures > 0,
		"detail": _("{0} active").format(structures), "route": "/app/salary-structure",
	})

	assigned = set(frappe.get_all("Salary Structure Assignment", {"docstatus": 1, "company": company}, pluck="employee"))
	all_active = set(frappe.get_all("Employee", {"company": company, "status": "Active"}, pluck="name"))
	unassigned = len(all_active - assigned)
	items.append({
		"key": "assignments", "label": _("All employees have a salary assignment"), "ok": unassigned == 0,
		"detail": _("All assigned") if unassigned == 0 else _("{0} without assignment").format(unassigned),
		"route": "/app/salary-structure-assignment",
	})

	payable = frappe.db.get_value("Company", company, "default_payroll_payable_account")
	items.append({
		"key": "payable_account", "label": _("Default Payroll Payable Account set"), "ok": bool(payable),
		"detail": payable or _("Set it on the Company"), "route": f"/app/company/{company}",
	})

	mapping = frappe.db.exists("Statutory Component Mapping", company)
	items.append({
		"key": "statutory_mapping", "label": _("Statutory Component Mapping (PT/LWF/TDS)"), "ok": bool(mapping),
		"detail": _("Configured") if mapping else _("Optional — enables auto PT/LWF & 24Q"),
		"route": "/app/statutory-component-mapping",
	})

	blocking = [i for i in items if not i["ok"] and i["key"] in ("employees", "structures", "payable_account")]
	return {"items": items, "ready": not blocking, "open_count": sum(1 for i in items if not i["ok"])}


def _employee_readiness(company):
	from indian_hrms_compliance.overrides.employee_master import get_employee_readiness_summary

	try:
		return get_employee_readiness_summary(company)
	except Exception:
		return {}


def _compliance(company, today):
	horizon = add_days(today, DUE_SOON_DAYS)
	fields = ["name", "return_type", "due_date", "filing_status", "period_label", "penalty_amount", "state"]
	overdue = frappe.get_all(
		"Compliance Filing",
		filters={"company": company, "due_date": ("<", today), "filing_status": ("not in", FILED_STATUSES)},
		fields=fields, order_by="due_date asc", limit=20,
	)
	due_soon = frappe.get_all(
		"Compliance Filing",
		filters={"company": company, "due_date": ("between", [today, horizon]), "filing_status": ("not in", FILED_STATUSES)},
		fields=fields, order_by="due_date asc", limit=20,
	)
	for r in overdue:
		r["days_late"] = (today - getdate(r["due_date"])).days
	return {"overdue": overdue, "due_soon": due_soon}


def _recent_runs(company):
	return frappe.get_all(
		"Payroll Entry",
		filters={"company": company},
		fields=["name", "start_date", "end_date", "status", "docstatus", "number_of_employees"],
		order_by="start_date desc", limit=5,
	)


def _suggested_period(company, today):
	"""Default the run to last completed month (payroll usually runs in arrears)."""
	first_this = get_first_day(today)
	prev_end = add_days(first_this, -1)
	prev_start = get_first_day(prev_end)
	return {"start_date": str(prev_start), "end_date": str(prev_end)}


# ----------------------------------------------------------------------- preview
@frappe.whitelist()
def get_run_preview(company, start_date, end_date, payroll_frequency="Monthly"):
	_guard()
	company = _resolve_company(company)
	filters = _payroll_filters(company, start_date, end_date, payroll_frequency)

	from indian_hrms_compliance.payroll.doctype.payroll_entry.payroll_entry import get_employee_list

	emps = get_employee_list(filters=filters, as_dict=True) or []
	emp_names = [e.get("employee") or e.get("name") for e in emps]

	# Projected base from each employee's current submitted SSA (rough gross proxy).
	base_by_emp = {}
	if emp_names:
		for row in frappe.get_all(
			"Salary Structure Assignment",
			filters={"employee": ("in", emp_names), "docstatus": 1, "company": company},
			fields=["employee", "base", "from_date"], order_by="from_date desc",
		):
			base_by_emp.setdefault(row.employee, flt(row.base))

	already = frappe.db.count(
		"Salary Slip",
		{"company": company, "start_date": start_date, "end_date": end_date, "docstatus": ("<", 2)},
	)
	return {
		"company": company,
		"start_date": start_date,
		"end_date": end_date,
		"eligible_count": len(emp_names),
		"projected_base_total": sum(base_by_emp.values()),
		"already_processed": already,
		"sample": [
			{"employee": n, "employee_name": next((e.get("employee_name") for e in emps if (e.get("employee") or e.get("name")) == n), n),
			 "base": base_by_emp.get(n, 0)}
			for n in emp_names[:10]
		],
	}


def _payroll_filters(company, start_date, end_date, payroll_frequency):
	company_currency = frappe.db.get_value("Company", company, "default_currency") or "INR"
	return frappe._dict({
		"company": company,
		"currency": company_currency,
		"salary_slip_based_on_timesheet": 0,
		"payroll_frequency": payroll_frequency,
		"start_date": start_date,
		"end_date": end_date,
		"payroll_payable_account": frappe.db.get_value("Company", company, "default_payroll_payable_account"),
	})


# --------------------------------------------------------------------------- run
@frappe.whitelist()
def run_payroll(company, start_date, end_date, payroll_frequency="Monthly"):
	"""Create a Payroll Entry, pull eligible employees, and generate draft Salary
	Slips. Returns the Payroll Entry so HR reviews & submits there (submission of
	many slips is enqueued by the Payroll Entry itself)."""
	_guard()
	company = _resolve_company(company)

	payable = frappe.db.get_value("Company", company, "default_payroll_payable_account")
	if not payable:
		frappe.throw(_("Set a Default Payroll Payable Account on the Company first."))
	cost_center = frappe.db.get_value("Company", company, "cost_center")
	currency = frappe.db.get_value("Company", company, "default_currency") or "INR"

	pe = frappe.new_doc("Payroll Entry")
	pe.company = company
	pe.posting_date = end_date
	pe.payroll_frequency = payroll_frequency
	pe.start_date = start_date
	pe.end_date = end_date
	pe.currency = currency
	pe.exchange_rate = 1
	pe.cost_center = cost_center
	pe.payroll_payable_account = payable
	pe.flags.ignore_permissions = True
	pe.insert()

	pe.fill_employee_details()
	count = len(pe.get("employees") or [])
	if not count:
		frappe.db.rollback()
		frappe.throw(_("No eligible employees for {0} – {1}. Check salary assignments / already-processed slips.").format(start_date, end_date))

	pe.save()
	pe.create_salary_slips()
	frappe.db.commit()
	return {"payroll_entry": pe.name, "employees": count, "route": f"/app/payroll-entry/{pe.name}"}
