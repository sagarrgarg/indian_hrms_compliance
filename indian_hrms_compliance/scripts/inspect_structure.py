"""Read-only inspector for a Salary Structure's statutory wage bases.

Answers one question precisely: are PF / Gratuity / ESI (and any other
statutory component) computed on Basic only, or do their formulas pull in the
Statutory Bonus (or gross ``base``) — which they must NOT, since PF wages and
gratuity wages exclude statutory bonus.

Mutates nothing. Safe to run on prod.

Usage
-----
    # list structures:
    bench --site hrms.rbcolour.com execute \
        indian_hrms_compliance.scripts.inspect_structure.run

    # inspect one (paste the output back to me):
    bench --site hrms.rbcolour.com execute \
        indian_hrms_compliance.scripts.inspect_structure.run \
        --kwargs "{'salary_structure': 'Hathras June 2026 Base Upto 21000'}"
"""

import re

import frappe

# components whose wage base is statutory and must exclude the bonus
_STATUTORY_HINTS = ("provident", "pf", "gratuit", "esi", "esic", "edli", "pension", "eps")
_BONUS_HINTS = ("bonus",)


def run(salary_structure=None):
	if not salary_structure:
		return _list()

	if not frappe.db.exists("Salary Structure", salary_structure):
		print(f"!! {salary_structure!r} not found.")
		return _list()

	doc = frappe.get_doc("Salary Structure", salary_structure)

	# map abbr -> component name, and find the statutory-bonus abbr(s)
	abbr_name, bonus_abbrs = {}, set()
	for r in list(doc.earnings) + list(doc.deductions):
		if r.abbr:
			abbr_name[r.abbr] = r.salary_component
		if _hit(r.salary_component, _BONUS_HINTS):
			bonus_abbrs.add(r.abbr)

	print("=" * 78)
	print(f"STRUCTURE: {salary_structure}   (base bounds {doc.min_base}/{doc.max_base}, active={doc.is_active}, docstatus={doc.docstatus})")
	print(f"Statutory Bonus abbr(s): {sorted(bonus_abbrs) or '(none found)'}")
	print("-" * 78)

	def dump(title, rows):
		print(title)
		for r in rows:
			f = (r.formula or "").strip()
			refs = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", f))
			flags = []
			is_statutory = _hit(r.salary_component, _STATUTORY_HINTS)
			if is_statutory:
				# does this statutory base reach the bonus, or gross `base`?
				if refs & bonus_abbrs:
					flags.append("!! INCLUDES STATUTORY BONUS")
				if "base" in refs:
					flags.append("~ uses gross `base` (includes bonus by definition — should key off Basic 'B')")
				if "gross_pay" in refs:
					flags.append("~ uses gross_pay (includes bonus — should key off Basic 'B')")
				if not flags:
					flags.append("ok: Basic-only")
			amt = f if r.amount_based_on_formula else f"(fixed {r.amount})"
			tag = "  <-- " + " ; ".join(flags) if flags else ""
			print(f"  {r.salary_component} [{r.abbr}] stat={r.statistical_component} :: {amt}{tag}")

	dump("EARNINGS:", doc.earnings)
	dump("DEDUCTIONS:", doc.deductions)
	print("=" * 78)
	print("Legend: statutory components (PF/Gratuity/ESI/...) SHOULD reference Basic")
	print("('B'), never the Bonus abbr, `base`, or `gross_pay`. Lines marked !! or ~")
	print("pull the bonus into the statutory wage base and need fixing.")
	return {"structure": salary_structure, "bonus_abbrs": sorted(bonus_abbrs)}


def _list():
	print("Salary Structures (name — company — docstatus — active):")
	for r in frappe.get_all(
		"Salary Structure",
		fields=["name", "company", "docstatus", "is_active"],
		order_by="name",
	):
		print(f"  {r.name:<45} {r.company or '(blank)':<38} ds={r.docstatus} {r.is_active}")
	print("\nPass salary_structure='<name>' to inspect one.")
	return None


def _hit(name, hints):
	n = (name or "").lower()
	return any(h in n for h in hints)
