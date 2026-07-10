# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Auto-provisioning of per-company Salary Component Account rows.

Every Salary Component should carry exactly one accounts row per Company so
the (expense) Account and (liability) Payable Account can be mapped per company
— see the employer-contribution provisioning in Payroll Entry.

The company set is auto-managed:
  * Salary Component ``validate``  -> ensure a row for every Company.
  * Company ``after_insert``       -> add the new company's row to every component.
  * ``after_migrate`` backfill     -> self-heal any missing (component, company) pair.

The form locks the grid (company read-only, no manual add), so users only fill
in the account values — the rows themselves are managed from here.
"""

import frappe


def ensure_component_rows(doc, method=None):
	"""doc_event: Salary Component ``validate``.

	Guarantee one ``accounts`` row per Company. Idempotent — only appends the
	missing companies, never touches account values the user has filled in.
	"""
	existing = {row.company for row in (doc.get("accounts") or []) if row.company}
	for company in frappe.get_all("Company", pluck="name"):
		if company not in existing:
			doc.append("accounts", {"company": company})


def _sync_component(name: str) -> None:
	doc = frappe.get_doc("Salary Component", name)
	before = len(doc.get("accounts") or [])
	ensure_component_rows(doc)
	if len(doc.get("accounts") or []) != before:
		doc.save(ignore_permissions=True)


def ensure_company_rows(doc, method=None):
	"""doc_event: Company ``after_insert`` — add the new company's row to every
	Salary Component."""
	for component in frappe.get_all("Salary Component", pluck="name"):
		_sync_component(component)


def backfill(*args, **kwargs):
	"""after_migrate: self-heal — ensure every (component, company) pair has a
	Salary Component Account row. Safe to run repeatedly."""
	for component in frappe.get_all("Salary Component", pluck="name"):
		_sync_component(component)
