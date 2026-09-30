"""One-off correction: restate PF / ESI on submitted Salary Slips, net pay unchanged.

Context
-------
The June 2026 structures computed PF and ESI wrongly on months with absent days:
Employer ESI was pro-rated twice (its formula used the already-earned Basic and
the row pro-rated it again), PF was a flat 12% x 15,000 pro-rated by payment
days instead of 12% x min(earned Basic, ceiling), and ESI was rounded to the
nearest rupee instead of up.

Salary was already paid on those slips, so net pay must not move. The script:

* Employer ESI / Employer PF (statistical rows — never in gross or net):
  set to the correct amount.
* Employee PF / Employee ESI: raised to the correct amount — the statutory
  share has to reach EPFO / ESIC. The short-deducted part cannot be recovered
  from later wages, so the employer bears it: an earning row
  "Statutory Contribution Borne by Employer" of the same total is added, and
  gross and total deduction move by that amount, leaving net pay identical.
  A deduction is never lowered.

    Employer ESI = ceil(esi_employer_rate x earned wage)
    Employee ESI = ceil(esi_employee_rate x earned wage)
    PF (both)    = round(pf_rate x min(earned wage, pf_ceiling))

where earned wage is the slip's Basic + DA. Submitted rows are not
allow_on_submit, so this is a direct data fix, recorded as a Comment on each
slip. GL is then rebuilt by ERPNext's Repost Accounting Ledger (Salary Slip is
enabled for it by the allow_salary_slip_repost patch), which reverses the old
rows and posts new ones — nothing is cancelled or deleted.

Usage (ALWAYS dry-run first)
----------------------------
    # 1. Dry run — lists every change, mutates nothing:
    bench --site hrms.rbcolour.com execute \
        indian_hrms_compliance.scripts.restate_employer_statutory.run \
        --kwargs "{'from_date': '2026-07-01', 'to_date': '2026-08-31', 'pf_ceiling': 15000}"

    # 2. Apply and queue the GL repost:
    bench --site hrms.rbcolour.com execute \
        indian_hrms_compliance.scripts.restate_employer_statutory.run \
        --kwargs "{'from_date': '2026-07-01', 'to_date': '2026-08-31', 'pf_ceiling': 15000, 'apply': 1, 'repost': 1}"

Optional kwargs
---------------
    company        limit to one Company (default: all)
    slips          list of Salary Slip names (overrides the date filter)
    pf_ceiling     PF wage ceiling in force for those months (default: HR Settings)
    employee_side  0 to restate only the employer rows (default 1)
    repost         with apply, create Repost Accounting Ledger docs (50 slips each,
                   per company) for the changed slips; they start automatically

Idempotent: rows already at the correct amount are skipped, so a second run is a no-op.
"""

import math

import frappe
from frappe.utils import flt

from indian_hrms_compliance.hr.doctype.statutory_component_mapping.statutory_component_mapping import (
	get_mapping_for_company,
)
from indian_hrms_compliance.overrides.salary_structure_validator import _is_pf_wage_row

REPOST_BATCH = 50  # ERPNext's MAX_VOUCHERS_PER_REPOST
OFFSET_COMPONENT = "Statutory Contribution Borne by Employer"


def run(
	apply=0,
	repost=0,
	company=None,
	from_date=None,
	to_date=None,
	slips=None,
	pf_ceiling=None,
	employee_side=1,
):
	apply, repost, employee_side = int(apply), int(repost), int(employee_side)
	settings = frappe.get_single("HR Settings")
	rates = frappe._dict(
		pf_ceiling=flt(pf_ceiling) or flt(settings.pf_wage_ceiling) or 15000,
		pf_employer=flt(settings.pf_employer_rate_pct or 12) / 100,
		pf_employee=flt(settings.pf_employee_rate_pct or 12) / 100,
		esi_employer=flt(settings.esi_employer_rate_pct or 3.25) / 100,
		esi_employee=flt(settings.esi_employee_rate_pct or 0.75) / 100,
	)
	if employee_side and not frappe.db.exists("Salary Component", OFFSET_COMPONENT):
		frappe.throw(f"Create the Salary Component '{OFFSET_COMPONENT}' first.")

	names = _slips_in_scope(company, from_date, to_date, slips)
	print(
		f"{'APPLY' if apply else 'DRY RUN'}: {len(names)} submitted slip(s); PF ceiling "
		f"{rates.pf_ceiling:,.0f}; PF {rates.pf_employee:.2%}/{rates.pf_employer:.2%}; "
		f"ESI {rates.esi_employee:.2%}/{rates.esi_employer:.2%}; employee side {'on' if employee_side else 'off'}"
	)

	changed, borne_total = {}, 0.0
	for name in names:
		slip = frappe.get_doc("Salary Slip", name)
		mapping = get_mapping_for_company(slip.company)
		wage = _earned_wage(slip, mapping)
		employer = _employer_changes(slip, mapping, wage, rates)
		employee = _employee_changes(slip, mapping, wage, rates) if employee_side else []
		if not (employer or employee):
			continue
		changed[name] = slip.company
		borne = flt(sum(new - old for _, old, new, _ in employee), 2)
		borne_total += borne
		for row, old, new, why in employer + employee:
			print(f"  {name:32} {row.salary_component:26} {old:>10,.2f} -> {new:>10,.2f}  ({why})")
		if borne:
			print(f"  {name:32} {'+ ' + OFFSET_COMPONENT:44} {borne:>10,.2f}  (net pay unchanged)")
		if apply:
			_apply(slip, employer, employee, borne)

	print(
		f"{len(changed)} slip(s) {'restated' if apply else 'would be restated'}; "
		f"employee share borne by employer {borne_total:,.2f}."
	)
	if apply:
		frappe.db.commit()
		if repost and changed:
			for docname in _queue_repost(changed):
				print(f"  Repost Accounting Ledger {docname} submitted (runs in background)")
	return {"slips": list(changed), "borne_by_employer": borne_total}


def _slips_in_scope(company, from_date, to_date, slips):
	if slips:
		names = frappe.parse_json(slips) if isinstance(slips, str) else list(slips)
		return frappe.get_all("Salary Slip", filters={"name": ("in", names), "docstatus": 1}, pluck="name")
	filters = {"docstatus": 1}
	if company:
		filters["company"] = company
	if from_date:
		filters["start_date"] = (">=", from_date)
	if to_date:
		filters["end_date"] = ("<=", to_date)
	return frappe.get_all("Salary Slip", filters=filters, order_by="start_date, name", pluck="name")


def _earned_wage(slip, mapping):
	"""Earned Basic + DA on the slip — the PF / ESI wage."""
	return sum(
		flt(r.amount)
		for r in slip.earnings
		if _is_pf_wage_row(r, mapping) and not r.statistical_component and not r.additional_salary
	)


def _employer_changes(slip, mapping, wage, rates):
	"""[(row, old, new, reason)] for employer rows off by a paisa or more."""
	esi_component = (mapping and mapping.esi_employer_component) or "Employer ESI"
	pf_component = (mapping and mapping.pf_employer_component) or "Employer Provident Fund"
	changes = []
	for row in slip.earnings:
		# Only statistical, out-of-total rows: never anything that feeds gross or net.
		if not (row.statistical_component and row.do_not_include_in_total) or row.additional_salary:
			continue
		if row.salary_component == esi_component:
			new = math.ceil(round(rates.esi_employer * wage, 6))
			why = f"{rates.esi_employer:.2%} of earned wage {wage:,.2f}, rounded up"
		elif row.salary_component == pf_component:
			new = round(rates.pf_employer * min(wage, rates.pf_ceiling))
			why = f"{rates.pf_employer:.0%} of min(earned wage {wage:,.2f}, {rates.pf_ceiling:,.0f})"
		else:
			continue
		if abs(flt(row.amount) - new) >= 0.01:
			changes.append((row, flt(row.amount), flt(new), why))
	return changes


def _employee_changes(slip, mapping, wage, rates):
	"""[(row, old, new, reason)] for employee PF / ESI rows that were under-deducted."""
	pf_component = (mapping and mapping.pf_employee_component) or "Provident Fund"
	esi_component = (mapping and mapping.esi_employee_component) or "Employee State Insurance"
	changes = []
	for row in slip.deductions:
		if row.statistical_component or row.additional_salary:
			continue
		if row.salary_component == pf_component:
			new = round(rates.pf_employee * min(wage, rates.pf_ceiling))
			why = f"{rates.pf_employee:.0%} of min(earned wage {wage:,.2f}, {rates.pf_ceiling:,.0f})"
		elif row.salary_component == esi_component:
			new = math.ceil(round(rates.esi_employee * wage, 6))
			why = f"{rates.esi_employee:.2%} of earned wage {wage:,.2f}, rounded up"
		else:
			continue
		# Only ever raise: what was deducted and paid out is never taken back.
		if new - flt(row.amount) >= 0.01:
			changes.append((row, flt(row.amount), flt(new), why))
	return changes


def _apply(slip, employer, employee, borne):
	net_before = flt(slip.net_pay, 2)
	for row, _, new, _ in employer + employee:
		frappe.db.set_value(
			"Salary Detail", row.name, {"amount": new, "default_amount": new}, update_modified=False
		)

	if borne:
		offset = frappe.get_doc(
			{
				"doctype": "Salary Detail",
				"name": frappe.generate_hash(length=10),
				"parent": slip.name,
				"parenttype": "Salary Slip",
				"parentfield": "earnings",
				"idx": max((r.idx for r in slip.earnings), default=0) + 1,
				"docstatus": 1,
				"salary_component": OFFSET_COMPONENT,
				"abbr": frappe.db.get_value("Salary Component", OFFSET_COMPONENT, "salary_component_abbr"),
				"amount": borne,
				"default_amount": borne,
				"depends_on_payment_days": 0,
				"is_tax_applicable": 1,
			}
		)
		offset.db_insert()
		ex = flt(slip.exchange_rate) or 1.0
		gross = flt(slip.gross_pay + borne, 2)
		total_deduction = flt(slip.total_deduction + borne, 2)
		if abs(gross - total_deduction - net_before) > 0.01:
			frappe.throw(f"{slip.name}: gross - deductions would not equal the paid net {net_before}")
		frappe.db.set_value(
			"Salary Slip",
			slip.name,
			{
				"gross_pay": gross,
				"base_gross_pay": flt(gross * ex, 2),
				"total_deduction": total_deduction,
				"base_total_deduction": flt(total_deduction * ex, 2),
			},
			update_modified=False,
		)

	if flt(frappe.db.get_value("Salary Slip", slip.name, "net_pay"), 2) != net_before:
		frappe.throw(f"{slip.name}: net pay changed — aborting")

	lines = [f"{r.salary_component}: {o:,.2f} → {n:,.2f} ({w})" for r, o, n, w in employer + employee]
	if borne:
		lines.append(f"{OFFSET_COMPONENT}: +{borne:,.2f} (employee share borne by employer)")
	slip.add_comment(
		"Comment",
		f"PF / ESI restated; net pay unchanged at {net_before:,.2f}:<br>" + "<br>".join(lines),
	)


def _queue_repost(changed):
	by_company = {}
	for name, company in changed.items():
		by_company.setdefault(company, []).append(name)
	created = []
	for company, names in by_company.items():
		for i in range(0, len(names), REPOST_BATCH):
			ral = frappe.get_doc(
				{
					"doctype": "Repost Accounting Ledger",
					"company": company,
					"delete_cancelled_entries": 0,
					"vouchers": [
						{"voucher_type": "Salary Slip", "voucher_no": n} for n in names[i : i + REPOST_BATCH]
					],
				}
			)
			ral.insert(ignore_permissions=True)
			ral.submit()
			created.append(ral.name)
	frappe.db.commit()
	return created
