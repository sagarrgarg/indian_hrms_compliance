# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Leave Period = Fiscal Year (India), with zero-touch allocation.

India's leave year is the fiscal year (1 Apr – 31 Mar). This module keeps a
national Leave Period aligned to each Fiscal Year (mirroring the national
Payroll Period). The current period is *derived* from the Fiscal Year via
``get_current_leave_period`` — it is never stored per company — and the
company's default Leave Policy is auto-granted to every active employee for the
period, so leave allocation is fully hands-off.

Wired in hooks.py:
    doc_events["Fiscal Year"]["after_insert"] += create_leave_period_from_fiscal_year
"""

import frappe
from frappe.utils import cint, getdate


def _hr_setting(field, default=None):
	"""Defensive HR Settings read — never raises if the field isn't there yet."""
	if not frappe.get_meta("HR Settings").has_field(field):
		return default
	val = frappe.db.get_single_value("HR Settings", field)
	return default if val is None else val


def ensure_leave_period_for_fiscal_year(fiscal_year):
	"""Get-or-create the national Leave Period matching a Fiscal Year's dates.
	Returns the Leave Period name (or None). Idempotent."""
	fy = frappe.db.get_value(
		"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not (fy and fy.year_start_date and fy.year_end_date):
		return None

	lp_name = frappe.db.get_value(
		"Leave Period", {"from_date": fy.year_start_date, "to_date": fy.year_end_date}, "name"
	)
	if not lp_name:
		lp = frappe.new_doc("Leave Period")
		lp.from_date = fy.year_start_date
		lp.to_date = fy.year_end_date
		lp.is_active = 1
		lp.flags.ignore_permissions = True
		lp.insert()
		lp_name = lp.name
	elif not frappe.db.get_value("Leave Period", lp_name, "is_active"):
		# Reactivate a reused period — it's the current FY's leave year.
		frappe.db.set_value("Leave Period", lp_name, "is_active", 1)
	return lp_name


def get_current_leave_period(on_date=None):
	"""The Leave Period for the Fiscal Year covering ``on_date`` (default: today).

	India's leave year IS the fiscal year, so the current period is derived here
	rather than stored per company — a single source of truth. Ensures the period
	exists. Returns the Leave Period name, or None when no Fiscal Year covers the
	date."""
	from erpnext.accounts.utils import get_fiscal_year

	target = getdate(on_date) if on_date else getdate()
	try:
		fy = get_fiscal_year(target, as_dict=True)
	except Exception:
		return None
	return ensure_leave_period_for_fiscal_year(fy.name)


def create_leave_period_from_fiscal_year(doc, method=None):
	"""Fiscal Year ``after_insert`` hook: create the matching Leave Period and
	(when auto-assign is on) grant the default Leave Policy to all active
	employees in the background."""
	lp_name = ensure_leave_period_for_fiscal_year(doc.name)
	if lp_name and cint(_hr_setting("auto_assign_leave_policy_on_activation")):
		frappe.enqueue(
			"indian_hrms_compliance.hr.leave_period_setup.grant_default_leave_for_period",
			queue="long",
			timeout=3600,
			leave_period=lp_name,
			enqueue_after_commit=True,
		)
	return lp_name


def grant_default_leave_for_period(leave_period):
	"""Create + submit a Leave Policy Assignment (each employee's company default
	Leave Policy) for every active Employee, for ``leave_period``. Pro-rates from
	the joining date. Idempotent — skips employees who already have an
	overlapping assignment or whose company has no default Leave Policy."""
	from indian_hrms_compliance.hr.doctype.leave_policy_assignment.leave_policy_assignment import (
		create_assignment,
	)

	period = frappe.db.get_value(
		"Leave Period", leave_period, ["from_date", "to_date"], as_dict=True
	)
	if not period:
		return {"granted": 0, "skipped": 0, "failed": 0, "no_period": True}

	# Prefetch everyone who already has an overlapping assignment in one query
	# (avoids an exists() per employee).
	already_assigned = set(
		frappe.get_all(
			"Leave Policy Assignment",
			filters={
				"docstatus": ("<", 2),
				"effective_from": ("<=", period.to_date),
				"effective_to": (">=", period.from_date),
			},
			pluck="employee",
		)
	)

	policy_by_company = {}
	granted = skipped = failed = 0

	for emp in frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "company", "date_of_joining", "leave_policy"],
	):
		if not emp.company or emp.name in already_assigned:
			skipped += 1
			continue
		if emp.company not in policy_by_company:
			policy_by_company[emp.company] = frappe.get_cached_value(
				"Company", emp.company, "default_leave_policy"
			)
		# The employee's own Leave Policy override wins; else the company default.
		policy = emp.leave_policy or policy_by_company[emp.company]
		if not policy:
			skipped += 1
			continue

		# Pro-rate from the joining date when the employee joined mid-period.
		effective_from = period.from_date
		if emp.date_of_joining and getdate(emp.date_of_joining) > getdate(period.from_date):
			effective_from = emp.date_of_joining

		savepoint = "grant_leave_for_period"
		try:
			frappe.db.savepoint(savepoint)
			assignment = create_assignment(
				emp.name,
				frappe._dict(
					assignment_based_on="Leave Period",
					leave_policy=policy,
					leave_period=leave_period,
					effective_from=effective_from,
					effective_to=period.to_date,
					carry_forward=0,
				),
			)
			assignment.submit()
			granted += 1
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			failed += 1
			frappe.log_error(
				title="Bulk leave grant failed",
				message=f"Employee: {emp.name}\nLeave Period: {leave_period}\n{frappe.get_traceback()}",
			)

	frappe.db.commit()
	return {"granted": granted, "skipped": skipped, "failed": failed}


@frappe.whitelist()
def setup_current_year_leave(grant=1):
	"""Manual entry point (HR Settings action / console): ensure the Leave Period
	for the current Fiscal Year exists + is the company default, and optionally
	grant leaves to all active employees now. Returns a summary."""
	frappe.only_for(["System Manager", "HR Manager"])
	from erpnext.accounts.utils import get_fiscal_year

	fy = get_fiscal_year(getdate(), as_dict=True)
	lp_name = ensure_leave_period_for_fiscal_year(fy.name)
	out = {"fiscal_year": fy.name, "leave_period": lp_name}
	if lp_name and cint(grant):
		out.update(grant_default_leave_for_period(lp_name))
	return out
