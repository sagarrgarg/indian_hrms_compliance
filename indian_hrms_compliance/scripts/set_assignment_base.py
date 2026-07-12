"""One-off apply-to-prod helper: set the Base on Salary Structure Assignments.

Context
-------
Base needs to be forced to a flat value (default ``21010`` — deliberately just
above the ₹21,000 ESI wage ceiling, to stress-test the statutory calculations)
across existing Salary Structure Assignments. ``base`` is NOT ``allow_on_submit``
and the doctype is submittable, so a normal form save cannot change it on a
submitted assignment — this script uses ``frappe.db.set_value`` (a direct data
fix) which is the supported way to correct a submitted field.

This lives in ``indian_hrms_compliance`` (not a patch) so it is only ever run
explicitly, never automatically during ``bench migrate``.

Usage (ALWAYS dry-run first)
----------------------------
    # 1. Dry run — reports what WOULD change, mutates nothing:
    bench --site hrms.rbcolour.com execute \
        indian_hrms_compliance.scripts.set_assignment_base.run

    # 2. Apply for real:
    bench --site hrms.rbcolour.com execute \
        indian_hrms_compliance.scripts.set_assignment_base.run \
        --kwargs "{'apply': 1}"

Optional kwargs
---------------
    base              target Base value (default 21010)
    company           limit to one Company (default: all)
    salary_structure  limit to assignments of one Salary Structure (default: all)
    from_date_on_or_after  limit to assignments effective on/after this date,
                           e.g. '2026-06-01' (default: all dates)
    only_if_above     if truthy, only touch assignments whose current base is
                      already > 21000 (leave lower bases untouched)
    pin_structure     if truthy, ALSO set min_base = max_base = base on the
                      Salary Structure(s) touched, locking future assignments to
                      this value (requires `salary_structure` or derives the set
                      from the matched assignments)

Notes
-----
* Only the Base field is changed. Already-generated Salary Slips are NOT
  recomputed — the new base applies to future payroll runs. Re-run payroll for
  any period you want recalculated.
* Idempotent: rows already at the target value are skipped and reported as such.
"""

import json

import frappe
from frappe.utils import flt


def run(
	apply=0,
	base=21010,
	company=None,
	salary_structure=None,
	from_date_on_or_after=None,
	only_if_above=0,
	pin_structure=0,
):
	apply = _truthy(apply)
	only_if_above = _truthy(only_if_above)
	pin_structure = _truthy(pin_structure)
	base = flt(base)

	filters = {}
	if company:
		filters["company"] = company
	if salary_structure:
		filters["salary_structure"] = salary_structure
	if from_date_on_or_after:
		filters["from_date"] = [">=", from_date_on_or_after]

	rows = frappe.get_all(
		"Salary Structure Assignment",
		filters=filters,
		fields=["name", "employee", "employee_name", "salary_structure", "base", "docstatus", "from_date"],
		order_by="from_date asc",
	)

	to_change, already, skipped_low = [], [], []
	for r in rows:
		current = flt(r.base)
		if only_if_above and current <= 21000:
			skipped_low.append(r)
			continue
		if current == base:
			already.append(r)
		else:
			to_change.append(r)

	print("=" * 72)
	print(f"Salary Structure Assignment base update  ->  target base = {base}")
	print(f"Filters: {filters or '(all assignments)'}")
	print(f"only_if_above=21000: {only_if_above}   pin_structure: {pin_structure}")
	print("-" * 72)
	print(f"Matched assignments : {len(rows)}")
	print(f"  already at target : {len(already)}")
	if only_if_above:
		print(f"  skipped (base<=21000): {len(skipped_low)}")
	print(f"  WILL change       : {len(to_change)}")
	print("-" * 72)
	for r in to_change[:50]:
		ds = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(r.docstatus, r.docstatus)
		print(f"  {r.name}  {r.employee_name or r.employee}  {flt(r.base)} -> {base}  [{ds}]")
	if len(to_change) > 50:
		print(f"  ... and {len(to_change) - 50} more")
	print("=" * 72)

	if not apply:
		print("DRY RUN — nothing was changed. Re-run with --kwargs \"{'apply': 1}\" to apply.")
		return {"matched": len(rows), "would_change": len(to_change), "already": len(already)}

	changed = 0
	for r in to_change:
		# Direct field update: bypasses the submit lock on `base`, which is the
		# intended behaviour for this corrective data fix.
		frappe.db.set_value("Salary Structure Assignment", r.name, "base", base, update_modified=True)
		changed += 1

	pinned = []
	if pin_structure:
		structures = (
			{salary_structure}
			if salary_structure
			else {r.salary_structure for r in rows if r.salary_structure}
		)
		for ss in structures:
			frappe.db.set_value(
				"Salary Structure",
				ss,
				{"min_base": base, "max_base": base},
				update_modified=True,
			)
			pinned.append(ss)

	frappe.db.commit()
	print(f"APPLIED — {changed} assignment(s) set to base {base}.")
	if pinned:
		print(f"Pinned min_base=max_base={base} on structures: {', '.join(pinned)}")
	print("Note: existing Salary Slips are unchanged; re-run payroll to recompute.")
	return {"matched": len(rows), "changed": changed, "pinned": pinned}


def _truthy(v):
	if isinstance(v, str):
		return v.strip().lower() in ("1", "true", "yes", "y", "on")
	return bool(v)
