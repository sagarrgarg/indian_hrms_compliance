# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Make every free-text `bank_name` a Link to the Bank master — without losing data.

Several doctypes stored the bank as free text: Employee, Employee Onboarding
Application, Form 24Q Challan, TDS Challan. The app-owned ones are already flipped
to Link in their JSON; Employee (erpnext core) is flipped here via a Property
Setter. This patch makes every existing value resolve:

  1. Trim each stored value in place.
  2. Seed a Bank record for every distinct trimmed name across all those sources
     (+ Bank Account.bank). Exact-after-trim — case/spelling variants stay
     separate; a review list is printed so HR can merge them via Bank rename.
  3. Property Setter: Employee.bank_name -> Link(Bank) (erpnext core untouched).

Idempotent, defensive, non-destructive. Runs post_model_sync, so the app-owned
fields are already Link by the time this seeds their Bank masters.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

# (doctype, fieldname) sources of a free-text bank name.
_BANK_TEXT_SOURCES = [
	("Employee", "bank_name"),
	("Employee Onboarding Application", "bank_name"),
	("Form 24Q Challan", "bank_name"),
	("TDS Challan", "bank_name"),
]


def execute():
	if not frappe.db.exists("DocType", "Bank"):
		return

	names = set()

	# 1 + 2: trim in place and collect the distinct set from every source.
	for dt, fn in _BANK_TEXT_SOURCES:
		if not frappe.db.exists("DocType", dt) or not frappe.get_meta(dt).has_field(fn):
			continue
		for name, val in frappe.get_all(
			dt, filters={fn: ["is", "set"]}, fields=["name", fn], as_list=True
		):
			trimmed = (val or "").strip()
			if not trimmed:
				continue
			names.add(trimmed)
			if trimmed != val:
				frappe.db.set_value(dt, name, fn, trimmed, update_modified=False)

	# Bank Account.bank rows are already Bank links — include them so nothing 404s.
	if frappe.db.has_column("Bank Account", "bank"):
		for b in frappe.get_all("Bank Account", filters={"bank": ["is", "set"]}, pluck="bank"):
			if b and b.strip():
				names.add(b.strip())

	# Seed a Bank master per distinct name (Bank autonames by bank_name).
	created = 0
	for nm in sorted(names):
		if not frappe.db.exists("Bank", nm):
			try:
				frappe.get_doc({"doctype": "Bank", "bank_name": nm}).insert(ignore_permissions=True)
				created += 1
			except Exception:
				frappe.log_error(title=f"Seed Bank failed: {nm}", message=frappe.get_traceback())

	# 3: Employee.bank_name -> Link(Bank) via Property Setters (erpnext core untouched).
	if frappe.get_meta("Employee").has_field("bank_name"):
		_ensure_prop("Employee", "bank_name", "fieldtype", "Link", "Select")
		_ensure_prop("Employee", "bank_name", "options", "Bank", "Text")
		frappe.clear_cache(doctype="Employee")

	# Review list: case-insensitive groups with more than one spelling.
	groups = {}
	for nm in names:
		groups.setdefault(nm.lower(), set()).add(nm)
	dupes = {k: sorted(v) for k, v in groups.items() if len(v) > 1}
	print(f"  bank_name -> Link(Bank): seeded {created} new bank(s), {len(names)} total.")
	if dupes:
		print("  Review near-duplicate Bank names (merge via Bank rename):")
		for _, spellings in sorted(dupes.items()):
			print("    " + " | ".join(spellings))


def _ensure_prop(doctype, fieldname, prop, value, prop_type):
	existing = frappe.db.exists(
		"Property Setter", {"doc_type": doctype, "field_name": fieldname, "property": prop}
	)
	if existing:
		if frappe.db.get_value("Property Setter", existing, "value") != value:
			frappe.db.set_value("Property Setter", existing, "value", value)
	else:
		make_property_setter(doctype, fieldname, prop, value, prop_type)
