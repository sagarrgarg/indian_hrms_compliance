"""Apply-to-prod helper: clone a Salary Structure, re-assign its employees on
the clone with a new Base, and delete the old structure + old assignments.

Why this exists
---------------
Base lives on the Salary Structure Assignment, not the structure, and a
submitted assignment's ``base`` cannot be edited via the form. It can be forced
with ``frappe.db.set_value`` (see ``set_assignment_base.py``), but if the linked
structure carries a ``[min_base, max_base]`` band the assignment validator HARD-
blocks a base outside it. The clean route — and the one used here — is:

    1. Clone the source structure verbatim (``frappe.copy_doc``), clearing the
       base bounds so the new base is always permitted, and submit it.
    2. For every assignment on the source structure, recreate it on the clone
       with the new base (default 21010) and, optionally, a new effective date
       (default 2026-06-01 — "June 2026"). The old assignment is removed first
       so the employee+from_date duplicate guard never trips.
    3. Delete the now-orphaned source structure.

Safe ONLY while no Salary Slips reference the structure — the script aborts if
any exist (override with ``force_with_slips=1`` if you truly mean to).

NOT fully atomic: the statutory validator's audit logger (``record_issue``)
calls ``frappe.db.commit()`` whenever it records an issue, so a mid-run crash
can leave the clone (and any assignments already recreated) committed. The
script mitigates this — it deletes each old assignment immediately before
creating its replacement, refuses to delete the source structure if ANY
assignment failed, and prints a full snapshot for every failure so it can be
recreated by hand. Always run the dry-run first and read the plan.

Lives in ``scripts/`` (not a patch) so it never runs during ``bench migrate``.

Usage — ALWAYS dry-run first
----------------------------
    # List candidate structures + their assignment counts (no source given):
    bench --site hrms.rbcolour.com execute \
        indian_hrms_compliance.scripts.clone_structure_and_reassign.run

    # Dry-run for one structure — shows the full plan, mutates nothing:
    bench --site hrms.rbcolour.com execute \
        indian_hrms_compliance.scripts.clone_structure_and_reassign.run \
        --kwargs "{'source_structure': 'Staff CTC Structure - KGOPL1'}"

    # Apply for real:
    bench --site hrms.rbcolour.com execute \
        indian_hrms_compliance.scripts.clone_structure_and_reassign.run \
        --kwargs "{'source_structure': 'Staff CTC Structure - KGOPL1', 'apply': 1}"

Key kwargs
----------
    source_structure  name of the structure to clone (required to do anything)
    new_name          name for the clone (default: '<source> (Base <base>)')
    base              new Base for every recreated assignment (default 21010)
    keep_base         if truthy, keep each assignment's existing base instead
    from_date         effective date for the new assignments (default
                      '2026-06-01'); pass '' to keep each old from_date
    delete_old        delete old assignments + old structure (default 1)
    clear_bounds      clear min_base/max_base on the clone (default 1)
    force_with_slips  proceed even if Salary Slips reference the structure (0)
    apply             actually perform changes (default 0 = dry run)
    commit            commit at the end (default 1; tests pass 0 + rollback)
"""

import frappe
from frappe.utils import flt, getdate


# fields copied verbatim from the old assignment onto the new one
_COPY_FIELDS = (
	"employee",
	"company",
	"currency",
	"variable",
	"income_tax_slab",
	"payroll_payable_account",
)


def run(
	source_structure=None,
	new_name=None,
	base=21010,
	keep_base=0,
	from_date="2026-06-01",
	delete_old=1,
	clear_bounds=1,
	force_with_slips=0,
	apply=0,
	commit=1,
):
	apply = _truthy(apply)
	keep_base = _truthy(keep_base)
	delete_old = _truthy(delete_old)
	clear_bounds = _truthy(clear_bounds)
	force_with_slips = _truthy(force_with_slips)
	commit = _truthy(commit)
	base = flt(base)

	if not source_structure:
		return _list_candidates()

	if not frappe.db.exists("Salary Structure", source_structure):
		print(f"!! Salary Structure {source_structure!r} does not exist.")
		return _list_candidates()

	if not new_name:
		new_name = f"{source_structure} (Base {int(base)})"

	# assignments to migrate — drafts + submitted (skip cancelled)
	assignments = frappe.get_all(
		"Salary Structure Assignment",
		filters={"salary_structure": source_structure, "docstatus": ["<", 2]},
		fields=["name", "employee", "employee_name", "base", "from_date", "docstatus"],
		order_by="from_date asc",
	)

	# safety: refuse if slips reference the structure
	slip_count = frappe.db.count("Salary Slip", {"salary_structure": source_structure})

	print("=" * 74)
	print(f"CLONE + RE-ASSIGN   source = {source_structure!r}")
	print(f"  new structure   : {new_name!r}   (clear_bounds={clear_bounds})")
	print(f"  new base        : {'keep existing' if keep_base else base}")
	print(f"  new from_date   : {from_date or 'keep existing'}")
	print(f"  delete old      : {delete_old}   (assignments + source structure)")
	print(f"  assignments     : {len(assignments)}")
	print(f"  salary slips ref: {slip_count}")
	print("-" * 74)
	for a in assignments:
		nb = flt(a.base) if keep_base else base
		fd = from_date or a.from_date
		ds = {0: "Draft", 1: "Submitted"}.get(a.docstatus, a.docstatus)
		print(f"  {a.employee_name or a.employee:<28} base {flt(a.base):>10.0f} -> {nb:<10.0f} from {fd}  [{ds}] ({a.name})")
	print("=" * 74)

	if slip_count and not force_with_slips:
		print(
			f"ABORT: {slip_count} Salary Slip(s) reference {source_structure!r}. "
			"Deleting/replacing would orphan them. Re-run with force_with_slips=1 "
			"only if you are certain."
		)
		return {"aborted": "salary_slips_exist", "slips": slip_count}

	if not apply:
		print("DRY RUN — nothing changed. Add 'apply': 1 to execute.")
		return {"source": source_structure, "assignments": len(assignments), "would_create": len(assignments)}

	# --- 1. clone the structure ------------------------------------------------
	src = frappe.get_doc("Salary Structure", source_structure)
	clone = frappe.copy_doc(src)
	clone.name = new_name  # autoname = Prompt -> name must be set explicitly
	clone.is_active = "Yes"
	if clear_bounds:
		clone.min_base = 0
		clone.max_base = 0
	clone.insert()
	if src.docstatus == 1:
		clone.submit()
	print(f"created structure {clone.name!r} (docstatus {clone.docstatus})")

	# --- 2. recreate assignments ----------------------------------------------
	created, failed = [], []
	for a in assignments:
		old = frappe.get_doc("Salary Structure Assignment", a.name)
		snapshot = {f: old.get(f) for f in _COPY_FIELDS}
		snapshot["base"] = old.base
		snapshot["from_date"] = old.from_date
		snapshot["cost_centers"] = [c.as_dict() for c in (old.get("payroll_cost_centers") or [])]

		# remove old first so the employee+from_date duplicate guard never trips
		if delete_old:
			if old.docstatus == 1:
				old.cancel()
			frappe.delete_doc("Salary Structure Assignment", a.name, force=1, ignore_permissions=True)

		try:
			new = frappe.new_doc("Salary Structure Assignment")
			for f in _COPY_FIELDS:
				new.set(f, snapshot[f])
			new.salary_structure = clone.name
			new.base = snapshot["base"] if keep_base else base
			new.from_date = from_date or snapshot["from_date"]
			for c in snapshot["cost_centers"]:
				new.append(
					"payroll_cost_centers",
					{"cost_center": c.get("cost_center"), "percentage": c.get("percentage")},
				)
			new.insert()
			new.submit()
			created.append((a.employee, new.name))
			print(f"  + {a.employee}: {new.name}  base {new.base}  from {new.from_date}")
		except Exception as exc:
			failed.append((a.employee, str(exc), snapshot))
			print(f"  ! {a.employee}: FAILED — {exc}")
			print(f"    recover from snapshot: {snapshot}")

	# --- 3. delete the source structure ---------------------------------------
	deleted_structure = None
	if delete_old and not failed:
		remaining = frappe.db.count("Salary Structure Assignment", {"salary_structure": source_structure})
		if remaining:
			print(f"  keeping {source_structure!r}: {remaining} assignment(s) still linked.")
		else:
			sdoc = frappe.get_doc("Salary Structure", source_structure)
			if sdoc.docstatus == 1:
				sdoc.cancel()
			frappe.delete_doc("Salary Structure", source_structure, force=1, ignore_permissions=True)
			deleted_structure = source_structure
			print(f"deleted source structure {source_structure!r}")
	elif failed:
		print(f"NOT deleting source structure — {len(failed)} assignment(s) failed; resolve first.")

	if commit:
		frappe.db.commit()
		print("COMMITTED.")
	else:
		print("commit=0 — caller is responsible for commit/rollback.")

	return {
		"new_structure": clone.name,
		"created": len(created),
		"failed": len(failed),
		"deleted_structure": deleted_structure,
	}


def _list_candidates():
	print("Candidate Salary Structures (name — company — docstatus — #assignments):")
	rows = frappe.get_all(
		"Salary Structure",
		fields=["name", "company", "docstatus", "is_active"],
		order_by="name",
	)
	for r in rows:
		n = frappe.db.count("Salary Structure Assignment", {"salary_structure": r.name, "docstatus": ["<", 2]})
		print(f"  {r.name:<40} {r.company or '(no company)':<38} ds={r.docstatus} active={r.is_active}  assignments={n}")
	print("\nPass source_structure='<name>' to plan a clone.")
	return {"candidates": len(rows)}


def _truthy(v):
	if isinstance(v, str):
		return v.strip().lower() in ("1", "true", "yes", "y", "on")
	return bool(v)
