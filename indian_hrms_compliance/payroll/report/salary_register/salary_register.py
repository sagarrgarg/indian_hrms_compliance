# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import json
import os

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate

import erpnext

salary_slip = frappe.qb.DocType("Salary Slip")
salary_detail = frappe.qb.DocType("Salary Detail")
salary_component = frappe.qb.DocType("Salary Component")


def execute(filters=None):
	if not filters:
		filters = {}

	currency = None
	if filters.get("currency"):
		currency = filters.get("currency")
	company_currency = erpnext.get_company_currency(filters.get("company"))

	salary_slips = get_salary_slips(filters, company_currency)
	if not salary_slips:
		return [], []

	earning_types, ded_types = get_earning_and_deduction_types(salary_slips)
	columns = get_columns(earning_types, ded_types)

	ss_earning_map = get_salary_slip_details(salary_slips, currency, company_currency, "earnings")
	ss_ded_map = get_salary_slip_details(salary_slips, currency, company_currency, "deductions")

	doj_map = get_employee_doj_map()

	data = []
	for ss in salary_slips:
		row = {
			"salary_slip_id": ss.name,
			"employee": ss.employee,
			"employee_name": ss.employee_name,
			"data_of_joining": doj_map.get(ss.employee),
			"branch": ss.branch,
			"department": ss.department,
			"designation": ss.designation,
			"company": ss.company,
			"start_date": ss.start_date,
			"end_date": ss.end_date,
			"leave_without_pay": ss.leave_without_pay,
			"absent_days": ss.absent_days,
			"payment_days": ss.payment_days,
			"currency": currency or company_currency,
			"total_loan_repayment": ss.total_loan_repayment,
		}

		update_column_width(ss, columns)

		for e in earning_types:
			row.update({frappe.scrub(e): ss_earning_map.get(ss.name, {}).get(e)})

		for d in ded_types:
			row.update({frappe.scrub(d): ss_ded_map.get(ss.name, {}).get(d)})

		if currency == company_currency:
			row.update(
				{
					"gross_pay": flt(ss.gross_pay) * flt(ss.exchange_rate),
					"total_deduction": (flt(ss.total_deduction) + flt(ss.total_loan_repayment))
					* flt(ss.exchange_rate),
					"net_pay": flt(ss.net_pay) * flt(ss.exchange_rate),
				}
			)

		else:
			row.update(
				{
					"gross_pay": ss.gross_pay,
					"total_deduction": flt(ss.total_deduction) + flt(ss.total_loan_repayment),
					"net_pay": ss.net_pay,
				}
			)

		data.append(row)

	return columns, data


def get_earning_and_deduction_types(salary_slips):
	salary_component_and_type = {_("Earning"): [], _("Deduction"): []}

	for salary_component in get_salary_components(salary_slips):
		component_type = get_salary_component_type(salary_component)
		salary_component_and_type[_(component_type)].append(salary_component)

	return sorted(salary_component_and_type[_("Earning")]), sorted(salary_component_and_type[_("Deduction")])


def update_column_width(ss, columns):
	if ss.branch is not None:
		columns[3].update({"width": 120})
	if ss.department is not None:
		columns[4].update({"width": 120})
	if ss.designation is not None:
		columns[5].update({"width": 120})
	if ss.leave_without_pay is not None:
		columns[9].update({"width": 120})


def get_columns(earning_types, ded_types):
	columns = [
		{
			"label": _("Salary Slip ID"),
			"fieldname": "salary_slip_id",
			"fieldtype": "Link",
			"options": "Salary Slip",
			"width": 150,
		},
		{
			"label": _("Employee"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{
			"label": _("Employee Name"),
			"fieldname": "employee_name",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Date of Joining"),
			"fieldname": "data_of_joining",
			"fieldtype": "Date",
			"width": 80,
		},
		{
			"label": _("Branch"),
			"fieldname": "branch",
			"fieldtype": "Link",
			"options": "Branch",
			"width": -1,
		},
		{
			"label": _("Department"),
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": -1,
		},
		{
			"label": _("Designation"),
			"fieldname": "designation",
			"fieldtype": "Link",
			"options": "Designation",
			"width": 120,
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 120,
		},
		{
			"label": _("Start Date"),
			"fieldname": "start_date",
			"fieldtype": "Data",
			"width": 80,
		},
		{
			"label": _("End Date"),
			"fieldname": "end_date",
			"fieldtype": "Data",
			"width": 80,
		},
		{
			"label": _("Leave Without Pay"),
			"fieldname": "leave_without_pay",
			"fieldtype": "Float",
			"width": 50,
		},
		{
			"label": _("Absent Days"),
			"fieldname": "absent_days",
			"fieldtype": "Float",
			"width": 50,
		},
		{
			"label": _("Payment Days"),
			"fieldname": "payment_days",
			"fieldtype": "Float",
			"width": 120,
		},
	]

	for earning in earning_types:
		columns.append(
			{
				"label": earning,
				"fieldname": frappe.scrub(earning),
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			}
		)

	columns.append(
		{
			"label": _("Gross Pay"),
			"fieldname": "gross_pay",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		}
	)

	for deduction in ded_types:
		columns.append(
			{
				"label": deduction,
				"fieldname": frappe.scrub(deduction),
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			}
		)

	if "lending" in frappe.get_installed_apps():
		columns.append(
			{
				"label": _("Loan Repayment"),
				"fieldname": "total_loan_repayment",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			}
		)

	columns.extend(
		[
			{
				"label": _("Total Deduction"),
				"fieldname": "total_deduction",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _("Net Pay"),
				"fieldname": "net_pay",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _("Currency"),
				"fieldtype": "Data",
				"fieldname": "currency",
				"options": "Currency",
				"hidden": 1,
			},
		]
	)
	return columns


def get_salary_components(salary_slips):
	return (
		frappe.qb.from_(salary_detail)
		.where((salary_detail.amount != 0) & (salary_detail.parent.isin([d.name for d in salary_slips])))
		.select(salary_detail.salary_component)
		.distinct()
	).run(pluck=True)


def get_salary_component_type(salary_component):
	return frappe.db.get_value("Salary Component", salary_component, "type", cache=True)


def get_salary_slips(filters, company_currency):
	doc_status = {"Draft": 0, "Submitted": 1, "Cancelled": 2}

	query = frappe.qb.from_(salary_slip).select(salary_slip.star)

	if filters.get("docstatus"):
		query = query.where(salary_slip.docstatus == doc_status[filters.get("docstatus")])

	if filters.get("from_date"):
		query = query.where(salary_slip.start_date >= filters.get("from_date"))

	if filters.get("to_date"):
		query = query.where(salary_slip.end_date <= filters.get("to_date"))

	if filters.get("company"):
		query = query.where(salary_slip.company == filters.get("company"))

	if filters.get("employee"):
		query = query.where(salary_slip.employee == filters.get("employee"))

	if filters.get("currency") and filters.get("currency") != company_currency:
		query = query.where(salary_slip.currency == filters.get("currency"))

	if filters.get("department"):
		query = query.where(salary_slip.department == filters["department"])

	if filters.get("designation"):
		query = query.where(salary_slip.designation == filters["designation"])

	if filters.get("branch"):
		query = query.where(salary_slip.branch == filters["branch"])

	salary_slips = query.run(as_dict=1)

	return salary_slips or []


def get_employee_doj_map():
	employee = frappe.qb.DocType("Employee")

	result = (frappe.qb.from_(employee).select(employee.name, employee.date_of_joining)).run()

	return frappe._dict(result)


def get_salary_slip_details(salary_slips, currency, company_currency, component_type):
	salary_slips = [ss.name for ss in salary_slips]

	result = (
		frappe.qb.from_(salary_slip)
		.join(salary_detail)
		.on(salary_slip.name == salary_detail.parent)
		.where((salary_detail.parent.isin(salary_slips)) & (salary_detail.parentfield == component_type))
		.select(
			salary_detail.parent,
			salary_detail.salary_component,
			salary_detail.amount,
			salary_slip.exchange_rate,
		)
	).run(as_dict=1)

	ss_map = {}

	for d in result:
		ss_map.setdefault(d.parent, frappe._dict()).setdefault(d.salary_component, 0.0)
		if currency == company_currency:
			ss_map[d.parent][d.salary_component] += flt(d.amount) * flt(
				d.exchange_rate if d.exchange_rate else 1
			)
		else:
			ss_map[d.parent][d.salary_component] += flt(d.amount)

	return ss_map


# ---------------------------------------------------------------------------
# Statutory Salary / Wages Register  (landscape PDF, employee-wise)
# ---------------------------------------------------------------------------

# Employer-contribution component classification (name-based, case-insensitive).
_EMPLOYER_PF_HINTS = ("employer provident", "employer pf", "employer's provident", "employer p f")
_EMPLOYER_ESI_HINTS = ("employer esi", "employer state insurance", "employer's esi", "employer e s i")
_EMPLOYER_LWF_HINTS = ("employer lwf", "employer labour welfare", "labour welfare fund - employer")

# EPS (pension) share of the 12% employer PF, i.e. 8.33 / 12.
_EPS_FRACTION = 8.33 / 12.0


def _employer_kind(name):
	n = (name or "").lower()
	if any(h in n for h in _EMPLOYER_PF_HINTS):
		return "pf"
	if any(h in n for h in _EMPLOYER_ESI_HINTS):
		return "esi"
	if any(h in n for h in _EMPLOYER_LWF_HINTS):
		return "lwf"
	return None


def _get_lwp_leave_types():
	return set(frappe.get_all("Leave Type", filters={"is_lwp": 1}, pluck="name"))


def _get_el_days(employee, from_date, to_date, lwp_types):
	"""Approved paid-leave (non-LWP) days that fall within the period."""
	fd, td = getdate(from_date), getdate(to_date)
	apps = frappe.get_all(
		"Leave Application",
		filters={
			"employee": employee,
			"status": "Approved",
			"docstatus": 1,
			"from_date": ["<=", td],
			"to_date": [">=", fd],
		},
		fields=["from_date", "to_date", "total_leave_days", "leave_type"],
	)
	total = 0.0
	for a in apps:
		if a.leave_type in lwp_types:
			continue
		a_fd, a_td = getdate(a.from_date), getdate(a.to_date)
		span = (a_td - a_fd).days + 1
		if span <= 0:
			continue
		# clip the application to the register period, then scale total_leave_days
		clip_start = max(a_fd, fd)
		clip_end = min(a_td, td)
		clipped = (clip_end - clip_start).days + 1
		if clipped <= 0:
			continue
		total += flt(a.total_leave_days) * (clipped / span)
	return round(total, 2)


def _get_company_header(company):
	c = frappe.db.get_value(
		"Company",
		company,
		[
			"company_name",
			"pan",
			"pf_establishment_code",
			"esic_establishment_code",
			"lwf_establishment_code",
		],
		as_dict=True,
	) or frappe._dict()
	addr_name = frappe.db.get_value(
		"Dynamic Link",
		{"link_doctype": "Company", "link_name": company, "parenttype": "Address"},
		"parent",
	)
	address = ""
	if addr_name:
		a = frappe.db.get_value(
			"Address", addr_name, ["address_line1", "city", "state", "pincode"], as_dict=True
		)
		if a:
			parts = [a.address_line1, a.city, a.state, a.pincode]
			address = ", ".join(p for p in parts if p)
	c["address"] = address
	c["name"] = company
	return c


def _period_label(from_date):
	d = getdate(from_date)
	return d.strftime("%B, %Y")


def _inr(v):
	"""Indian-grouped number, 2 decimals, no currency symbol. Blank for zero."""
	v = flt(v)
	if v == 0:
		return ""
	neg = v < 0
	s = "{:.2f}".format(abs(v))
	intp, dec = s.split(".")
	if len(intp) > 3:
		last3 = intp[-3:]
		rest = intp[:-3]
		import re

		rest = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", rest)
		intp = rest + "," + last3
	out = intp + "." + dec
	return ("-" + out) if neg else out


@frappe.whitelist()
def get_wages_register_html(filters=None):
	"""Render the employee-wise statutory Salary / Wages Register as a
	standalone, print-ready (landscape) HTML document."""
	if isinstance(filters, str):
		filters = json.loads(filters)
	filters = filters or {}

	company = filters.get("company")
	company_currency = erpnext.get_company_currency(company) if company else None

	slips = get_salary_slips(filters, company_currency)
	if not slips:
		frappe.throw(_("No salary slips found for the selected filters."))

	# full component rows (incl. statistical) per slip, in idx order
	slip_names = [s.name for s in slips]
	detail_rows = frappe.get_all(
		"Salary Detail",
		filters={"parent": ["in", slip_names]},
		fields=[
			"parent",
			"parentfield",
			"salary_component",
			"amount",
			"default_amount",
			"statistical_component",
			"do_not_include_in_total",
			"idx",
		],
		order_by="parentfield, idx asc",
	)

	details = {}  # slip -> {"earn":[rows], "ded":[rows]}
	for r in detail_rows:
		bucket = details.setdefault(r.parent, {"earn": [], "ded": []})
		key = "earn" if r.parentfield == "earnings" else "ded"
		bucket[key].append(r)

	# discover ordered, dynamic column sets
	earn_cols, ded_cols = [], []
	has_employer = {"pf": False, "esi": False, "lwf": False}
	for s in slips:
		d = details.get(s.name, {"earn": [], "ded": []})
		for r in d["earn"]:
			kind = _employer_kind(r.salary_component)
			if kind:
				has_employer[kind] = True
				continue
			if r.statistical_component or r.do_not_include_in_total:
				continue
			if r.salary_component not in earn_cols:
				earn_cols.append(r.salary_component)
		for r in d["ded"]:
			if r.statistical_component or r.do_not_include_in_total:
				continue
			if r.salary_component not in ded_cols:
				ded_cols.append(r.salary_component)

	emp_cols = []
	if has_employer["pf"]:
		emp_cols += ["Pension (EPS)", "EPF Difference"]
	if has_employer["esi"]:
		emp_cols += ["ESI (Employer)"]
	if has_employer["lwf"]:
		emp_cols += ["LWF (Employer)"]

	lwp_types = _get_lwp_leave_types()

	emp_fields = [
		"employee_name",
		"father_or_husband_name",
		"designation",
		"provident_fund_account",
		"uan_number",
		"esic_ip_number",
		"date_of_joining",
	]

	rows = []
	totals = frappe._dict(
		rate={c: 0.0 for c in earn_cols},
		rate_total=0.0,
		earn={c: 0.0 for c in earn_cols},
		gross=0.0,
		ded={c: 0.0 for c in ded_cols},
		ded_total=0.0,
		emp={c: 0.0 for c in emp_cols},
		emp_total=0.0,
		net=0.0,
	)

	for i, s in enumerate(slips, start=1):
		d = details.get(s.name, {"earn": [], "ded": []})
		emp = frappe.db.get_value("Employee", s.employee, emp_fields, as_dict=True) or frappe._dict()

		rate = {c: 0.0 for c in earn_cols}
		earn = {c: 0.0 for c in earn_cols}
		empl = {c: 0.0 for c in emp_cols}
		employer_pf_amt = 0.0

		for r in d["earn"]:
			kind = _employer_kind(r.salary_component)
			if kind == "pf":
				employer_pf_amt += flt(r.amount)
				continue
			if kind == "esi":
				if "ESI (Employer)" in empl:
					empl["ESI (Employer)"] += flt(r.amount)
				continue
			if kind == "lwf":
				if "LWF (Employer)" in empl:
					empl["LWF (Employer)"] += flt(r.amount)
				continue
			if r.statistical_component or r.do_not_include_in_total:
				continue
			if r.salary_component in rate:
				rate[r.salary_component] += flt(r.default_amount)
				earn[r.salary_component] += flt(r.amount)

		if employer_pf_amt and "Pension (EPS)" in empl:
			pension = round(employer_pf_amt * _EPS_FRACTION)
			empl["Pension (EPS)"] += pension
			empl["EPF Difference"] += employer_pf_amt - pension

		ded = {c: 0.0 for c in ded_cols}
		for r in d["ded"]:
			if r.statistical_component or r.do_not_include_in_total:
				continue
			if r.salary_component in ded:
				ded[r.salary_component] += flt(r.amount)

		rate_total = sum(rate.values())
		emp_total = sum(empl.values())
		ded_total = flt(s.total_deduction) + flt(s.total_loan_repayment)
		gross = flt(s.gross_pay)
		net = flt(s.net_pay)

		row = frappe._dict(
			sno=i,
			salary_slip=s.name,
			employee=s.employee,
			employee_name=emp.employee_name or s.employee_name,
			father_or_husband_name=emp.father_or_husband_name or "",
			designation=emp.designation or s.designation or "",
			pf_no=emp.provident_fund_account or "",
			esic_no=emp.esic_ip_number or "",
			uan=emp.uan_number or "",
			doj=formatdate(emp.date_of_joining) if emp.date_of_joining else "",
			wd=flt(s.total_working_days),
			el=_get_el_days(s.employee, s.start_date, s.end_date, lwp_types),
			lwp=flt(s.leave_without_pay),
			pd=flt(s.payment_days),
			rate=rate,
			rate_total=rate_total,
			earn=earn,
			gross=gross,
			ded=ded,
			ded_total=ded_total,
			emp=empl,
			emp_total=emp_total,
			net=net,
		)
		rows.append(row)

		for c in earn_cols:
			totals.rate[c] += rate[c]
			totals.earn[c] += earn[c]
		for c in ded_cols:
			totals.ded[c] += ded[c]
		for c in emp_cols:
			totals.emp[c] += empl[c]
		totals.rate_total += rate_total
		totals.gross += gross
		totals.ded_total += ded_total
		totals.emp_total += emp_total
		totals.net += net

	# drop all-zero component columns (e.g. a TDS row that is 0 for everyone)
	earn_cols = [c for c in earn_cols if totals.rate[c] or totals.earn[c]]
	ded_cols = [c for c in ded_cols if totals.ded[c]]
	emp_cols = [c for c in emp_cols if totals.emp[c]]

	context = {
		"company": _get_company_header(company),
		"period_label": _period_label(filters.get("from_date")),
		"from_date": formatdate(filters.get("from_date")),
		"to_date": formatdate(filters.get("to_date")),
		"earn_cols": earn_cols,
		"ded_cols": ded_cols,
		"emp_cols": emp_cols,
		"rows": rows,
		"totals": totals,
		"currency": company_currency,
		"printed_on": formatdate(frappe.utils.nowdate()),
		"inr": _inr,
	}

	template = _read_template("wages_register.html")
	return frappe.render_template(template, context)


def _read_template(name):
	path = os.path.join(os.path.dirname(__file__), name)
	with open(path, encoding="utf-8") as f:
		return f.read()


# ---------------------------------------------------------------------------
# Consolidated "Grand Total of Salary / Wages" summary  (company + period)
# ---------------------------------------------------------------------------


def _is_vpf(component_name):
	n = (component_name or "").lower()
	return "voluntary" in n or n == "vpf" or "vpf" in n


def _is_pf_employee(component_name):
	n = (component_name or "").lower()
	return (
		("provident fund" in n or n == "pf" or "epf" in n)
		and "employer" not in n
		and "voluntary" not in n
		and "loan" not in n
	)


def _is_esi_employee(component_name):
	n = (component_name or "").lower()
	return ("state insurance" in n or "esi" in n) and "employer" not in n


@frappe.whitelist()
def get_payroll_summary_html(filters=None):
	"""Render the company-wise, period-wise consolidated payroll grand-total
	summary (earnings, deductions, employer contributions, PF challan heads,
	ESIC challan) as a print-ready HTML document.

	All figures are derived from the ACTUAL Salary Slip component amounts so
	the sheet is internally consistent (Employer Contributions == the PF/ESIC
	detail boxes) and matches the money actually deducted/contributed. PF/ESI
	statutory RATES (EPS, EDLI, admin, ESI %) are read from HR Settings via
	the ECR/ESI generators; only the wage bases come from the slips (which
	auto-respects a ₹15,000 PF cap when the structure caps it)."""
	if isinstance(filters, str):
		filters = json.loads(filters)
	filters = filters or {}

	company = filters.get("company")
	company_currency = erpnext.get_company_currency(company) if company else None

	slips_meta = get_salary_slips(filters, company_currency)
	if not slips_meta:
		frappe.throw(_("No salary slips found for the selected filters."))
	slip_docs = [frappe.get_doc("Salary Slip", s.name) for s in slips_meta]

	from indian_hrms_compliance.hr.doctype.statutory_component_mapping.statutory_component_mapping import (
		get_mapping_for_company,
	)
	from indian_hrms_compliance.overrides import esi_generator as esig
	from indian_hrms_compliance.overrides import pf_ecr_generator as pfg

	mapping = get_mapping_for_company(company)
	pf_emp_comp = mapping.pf_employee_component if mapping else None
	esi_emp_comp = mapping.esi_employee_component if mapping else None

	# --- pass over slips: earnings/deductions totals + actual statutory amts
	earn_tot, ded_tot = {}, {}
	gross = ded_total = net = 0.0
	lwf_employer_total = 0.0
	per_pf = []  # (pf_employee, vpf, employer_pf) per PF member
	per_esi = []  # (esi_employee, employer_esi) per ESI member

	for d in slip_docs:
		slip_pf_emp = slip_vpf = slip_er_pf = 0.0
		slip_esi_emp = slip_er_esi = slip_lwf_er = 0.0

		for r in d.earnings:
			kind = _employer_kind(r.salary_component)
			if kind == "pf":
				slip_er_pf += flt(r.amount)
				continue
			if kind == "esi":
				slip_er_esi += flt(r.amount)
				continue
			if kind == "lwf":
				slip_lwf_er += flt(r.amount)
				continue
			if r.statistical_component or r.do_not_include_in_total:
				continue
			earn_tot[r.salary_component] = earn_tot.get(r.salary_component, 0.0) + flt(r.amount)

		for r in d.deductions:
			kind = _employer_kind(r.salary_component)
			if kind == "pf":
				slip_er_pf += flt(r.amount)
				continue
			if kind == "esi":
				slip_er_esi += flt(r.amount)
				continue
			if kind == "lwf":
				slip_lwf_er += flt(r.amount)
				continue
			if r.statistical_component or r.do_not_include_in_total:
				continue
			name = r.salary_component
			ded_tot[name] = ded_tot.get(name, 0.0) + flt(r.amount)
			if _is_vpf(name):
				slip_vpf += flt(r.amount)
			elif (pf_emp_comp and name == pf_emp_comp) or (not pf_emp_comp and _is_pf_employee(name)):
				slip_pf_emp += flt(r.amount)
			elif (esi_emp_comp and name == esi_emp_comp) or (not esi_emp_comp and _is_esi_employee(name)):
				slip_esi_emp += flt(r.amount)

		gross += flt(d.gross_pay)
		ded_total += flt(d.total_deduction) + flt(d.get("total_loan_repayment"))
		net += flt(d.net_pay)
		lwf_employer_total += slip_lwf_er
		if slip_pf_emp or slip_er_pf:
			per_pf.append((slip_pf_emp, slip_vpf, slip_er_pf))
		if slip_esi_emp or slip_er_esi:
			per_esi.append((slip_esi_emp, slip_er_esi))

	total_earning = sum(earn_tot.values())

	# --- PF challan heads (actual amounts + HR-Settings statutory rates) ----
	pf = None
	if per_pf:
		emp_rate = flt(pfg._hr_setting("pf_employee_rate_pct")) / 100.0 or 0.12
		er_rate = flt(pfg._hr_setting("pf_employer_rate_pct")) / 100.0 or 0.12
		eps_rate = flt(pfg._hr_setting("pf_eps_rate_pct")) / 100.0
		edli_rate = flt(pfg._hr_setting("pf_edli_rate_pct")) / 100.0
		edli_cap = flt(pfg._hr_setting("pf_edli_per_member_cap") or 75)
		admin_rate = flt(pfg._hr_setting("pf_admin_charges_pct")) / 100.0
		admin_min = flt(pfg._hr_setting("pf_admin_charges_min"))
		ceiling = flt(pfg._hr_setting("pf_wage_ceiling"))
		epf_ac01 = pension_ac10 = diff_ac01 = 0.0
		wages_01 = wages_10 = edli_ac21 = 0.0
		for pe, vp, erpf in per_pf:
			# imply employer share = employee share (standard 12%) when the
			# structure does not model an explicit employer-PF component.
			employer_pf = erpf if erpf else pe
			epf_wages = (employer_pf / er_rate) if (employer_pf and er_rate) else (
				(pe / emp_rate) if emp_rate else 0.0
			)
			eps_wages = min(epf_wages, ceiling) if ceiling else epf_wages
			pension = round(eps_wages * eps_rate)
			epf_ac01 += pe + vp
			pension_ac10 += pension
			diff_ac01 += employer_pf - pension
			wages_01 += epf_wages
			wages_10 += eps_wages
			edli_ac21 += min(round(eps_wages * edli_rate), edli_cap)
		admin_ac02 = max(round(wages_10 * admin_rate), admin_min)
		edli_admin_ac22 = 0.0  # A/c-22 abolished (rate 0) — kept for form parity
		pf = {
			"count": len(per_pf),
			"wages_01": wages_01,
			"wages_10": wages_10,
			"wages_21": wages_10,
			"epf_ac01": epf_ac01,
			"pension_ac10": pension_ac10,
			"diff_ac01": diff_ac01,
			"admin_ac02": admin_ac02,
			"edli_ac21": edli_ac21,
			"edli_admin_ac22": edli_admin_ac22,
			"total": epf_ac01 + pension_ac10 + diff_ac01 + admin_ac02 + edli_ac21 + edli_admin_ac22,
		}

	# --- ESIC challan (actual amounts + HR-Settings rates) ------------------
	esi = None
	if per_esi:
		emp_esi_rate = flt(esig._hr_setting("esi_employee_rate_pct")) / 100.0
		er_esi_rate = flt(esig._hr_setting("esi_employer_rate_pct")) / 100.0
		employee = employer = wages = 0.0
		for ee, eer in per_esi:
			employer_esi = eer if eer else (ee / emp_esi_rate * er_esi_rate if (ee and emp_esi_rate) else 0.0)
			wage = (ee / emp_esi_rate) if (ee and emp_esi_rate) else (
				(eer / er_esi_rate) if (eer and er_esi_rate) else 0.0
			)
			employee += ee
			employer += employer_esi
			wages += wage
		esi = {
			"count": len(per_esi),
			"wages": wages,
			"employee": employee,
			"employer": employer,
			"total": employee + employer,
		}

	# --- Employer Contributions box — sourced from the SAME PF/ESI figures --
	employer = {
		"Pension": pf["pension_ac10"] if pf else 0.0,
		"Difference": pf["diff_ac01"] if pf else 0.0,
		"ESIC": esi["employer"] if esi else 0.0,
		"LWFER": lwf_employer_total,
	}

	context = {
		"company": _get_company_header(company),
		"period_label": _period_label(filters.get("from_date")),
		"earn_tot": earn_tot,
		"total_earning": total_earning,
		"ded_tot": ded_tot,
		"ded_total": ded_total,
		"employer": employer,
		"employer_total": sum(employer.values()),
		"net": net,
		"total_employee": len(slip_docs),
		"pf": pf,
		"esi": esi,
		"printed_on": formatdate(frappe.utils.nowdate()),
		"inr": _inr,
	}
	template = _read_template("payroll_summary.html")
	return frappe.render_template(template, context)
