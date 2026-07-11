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


@frappe.whitelist()
def sync_salary_component_accounts():
	"""Manual trigger (HR Settings → Actions → 'Sync Salary Component Accounts').

	Ensures one accounts row per Company for every Salary Component and
	creates/fills the default Account / Payable Account, without waiting for a
	migrate. Idempotent — only fills empty fields, only creates missing
	accounts. Returns a short summary for the UI.
	"""
	frappe.only_for(["System Manager", "HR Manager"])

	empty_filter = {"account": ["is", "not set"]}
	before_empty = frappe.db.count("Salary Component Account", empty_filter)

	for component in frappe.get_all("Salary Component", pluck="name"):
		_sync_component(component)
	ensure_default_accounts()

	after_empty = frappe.db.count("Salary Component Account", empty_filter)
	return {
		"rows_total": frappe.db.count("Salary Component Account"),
		"accounts_filled": max(before_empty - after_empty, 0),
		"account_empty_remaining": after_empty,
	}


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
	Salary Component, then fill default accounts for the new company."""
	for component in frappe.get_all("Salary Component", pluck="name"):
		_sync_component(component)
	ensure_default_accounts(company=doc.name)


def backfill(*args, **kwargs):
	"""after_migrate: self-heal — ensure every (component, company) pair has a
	Salary Component Account row, then fill default accounts. Safe to re-run."""
	for component in frappe.get_all("Salary Component", pluck="name"):
		_sync_component(component)
	ensure_default_accounts()


# ---------------------------------------------------------------------------
# Default account auto-provisioning
# ---------------------------------------------------------------------------
#
# Fill the (expense) Account and (liability) Payable Account on each row so
# payroll booking works out of the box, creating the accounts when missing:
#   * in-hand earnings (non-statistical) -> Dr "Salary Expenses"; net already
#     lands in the company's Payroll Payable.
#   * deductions -> "<Component> Payable" (the account ERPNext credits).
#   * statistical employer components -> Dr "Salary Expenses",
#     Cr "<Component> Payable" (see Payroll Entry provisioning).
# Only empty fields are filled — user-set accounts are never overwritten.

_SHARED_EXPENSE = "Salary Expenses"


def _ensure_account(company, account_name, parent_group, root_type):
	"""Get-or-create a leaf Account under the named group. Returns the account
	name, or None if the parent group doesn't exist for this company."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	full = f"{account_name} - {abbr}"
	if frappe.db.exists("Account", full):
		return full
	parent = frappe.db.get_value(
		"Account", {"company": company, "account_name": parent_group, "is_group": 1}, "name"
	)
	if not parent:
		return None
	acc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": account_name,
			"company": company,
			"parent_account": parent,
			"is_group": 0,
			"root_type": root_type,
			"account_currency": frappe.get_cached_value("Company", company, "default_currency"),
		}
	)
	acc.insert(ignore_permissions=True)
	return acc.name


def ensure_default_accounts(company=None):
	"""Fill empty Account / Payable Account on Salary Component Account rows,
	creating '<Component> Payable' liabilities and a shared 'Salary Expenses'
	as needed. Scope to one company when given. Idempotent."""
	comps = frappe.get_all("Salary Component", fields=["name", "type", "statistical_component"])
	for comp in comps:
		filters = {"parent": comp.name}
		if company:
			filters["company"] = company
		rows = frappe.get_all(
			"Salary Component Account", filters=filters,
			fields=["name", "company", "account", "payable_account"],
		)
		for row in rows:
			co = row.company
			payable_name = f"{comp.name} Payable"
			if comp.type == "Deduction":
				if not row.account:
					acc = _ensure_account(co, payable_name, "Current Liabilities", "Liability")
					if acc:
						frappe.db.set_value("Salary Component Account", row.name, "account", acc)
			elif comp.statistical_component:
				if not row.account:
					exp = _ensure_account(co, _SHARED_EXPENSE, "Indirect Expenses", "Expense")
					if exp:
						frappe.db.set_value("Salary Component Account", row.name, "account", exp)
				if not row.payable_account:
					pay = _ensure_account(co, payable_name, "Current Liabilities", "Liability")
					if pay:
						frappe.db.set_value("Salary Component Account", row.name, "payable_account", pay)
			else:  # in-hand earning
				if not row.account:
					exp = _ensure_account(co, _SHARED_EXPENSE, "Indirect Expenses", "Expense")
					if exp:
						frappe.db.set_value("Salary Component Account", row.name, "account", exp)
