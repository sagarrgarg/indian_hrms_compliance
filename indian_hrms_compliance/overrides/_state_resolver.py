# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Employee → Indian State resolver — Phase 6B-2.

Used by PT Return + LWF Return generators to attribute each
employee's monthly contribution to the right state. Resolution order:

  1. Address linked to Employee (via Dynamic Link) → Address.gst_state.
  2. Address linked to the employee's Company → Address.gst_state.
  3. HR Settings.default_pt_state (Phase 6A field — only sensible for
     single-state Companies; multi-state shops should set per-employee
     Address).

Returns the Indian State *name* (= state_code, e.g. 'KA'), or None.
"""

import frappe


# Cache the state_name → state_code mapping once per request — used by
# resolve_employee_state to convert "Karnataka" (from Address.gst_state)
# to "KA" (Indian State name).
def _state_name_to_code_map():
	"""Return {state_name: state_code} for every Indian State row. Frappe
	caches the cached_value internally; this helper just shapes it."""
	cache_key = "indian_state_name_to_code"
	cached = frappe.cache().get_value(cache_key)
	if cached:
		return cached
	rows = frappe.get_all("Indian State", fields=["name", "state_name"])
	mapping = {r.state_name: r.name for r in rows}
	# Also accept ISO codes verbatim (in case Address.gst_state has been set
	# to 'KA' directly).
	for r in rows:
		mapping.setdefault(r.name, r.name)
	frappe.cache().set_value(cache_key, mapping)
	return mapping


def _address_state_via_dynamic_link(doctype, name):
	"""Return the gst_state of the first Address linked to (doctype, name)
	via Dynamic Link, or None. Preference: Permanent > Office > anything."""
	addresses = frappe.db.sql(
		"""
		SELECT a.name, a.address_type, a.gst_state, a.state, a.country
		FROM `tabAddress` a
		JOIN `tabDynamic Link` dl ON dl.parent = a.name AND dl.parenttype = 'Address'
		WHERE dl.link_doctype = %s AND dl.link_name = %s
		""",
		(doctype, name),
		as_dict=True,
	)
	if not addresses:
		return None

	# Preference order — Permanent first (employee's home state for taxation
	# is normally the residence), then Office, then anything.
	preferred_order = ["Permanent", "Office", "Personal", "Billing", "Shipping"]
	addresses.sort(key=lambda a: preferred_order.index(a.address_type) if a.address_type in preferred_order else 99)
	for addr in addresses:
		# gst_state is the canonical India-only state field on Address; falls
		# back to the free-text 'state' if gst_state unset.
		val = addr.gst_state or addr.state
		if val:
			return val
	return None


def _hr_setting_default_pt_state():
	"""Fallback to HR Settings.default_pt_state if it's set. We check meta
	first to avoid throwing when the field doesn't yet exist (test envs)."""
	meta = frappe.get_meta("HR Settings")
	if not meta.get_field("default_pt_state"):
		return None
	val = frappe.db.get_single_value("HR Settings", "default_pt_state")
	return val or None


def resolve_employee_state(employee_name):
	"""Resolve the Indian State for an Employee.

	Returns the Indian State *name* (which equals its state_code, e.g.
	'KA'), or None if nothing resolves. Caller logs a None to exceptions
	so HR can correct the master data.
	"""
	if not employee_name:
		return None

	# Step 1 — Employee-linked Address.
	state_text = _address_state_via_dynamic_link("Employee", employee_name)
	if not state_text:
		# Step 2 — Company-linked Address.
		company = frappe.db.get_value("Employee", employee_name, "company")
		if company:
			state_text = _address_state_via_dynamic_link("Company", company)

	if state_text:
		code_map = _state_name_to_code_map()
		# Accept either the full name ("Karnataka") or the code ("KA").
		if state_text in code_map:
			return code_map[state_text]

	# Step 3 — HR Settings default.
	default_state = _hr_setting_default_pt_state()
	if default_state:
		return default_state

	return None
