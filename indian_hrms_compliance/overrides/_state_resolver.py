# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Employee → Indian State resolver — Phase 6B-2.

Used by slip-time PT / LWF and the PT / LWF Return generators to attribute
each employee's contribution to the right state. PT and LWF follow the place
of WORK, not residence, so resolution order is:

  1. Address linked to the employee's Branch (via Dynamic Link).
  2. The employee's own "Office" Address.
  3. Address linked to the employee's Company.
  4. HR Settings.default_pt_state.

An employee's Permanent / Personal address is never used.

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


def _address_state_via_dynamic_link(doctype, name, address_types=None):
	"""Return the gst_state of the first Address linked to (doctype, name)
	via Dynamic Link, or None. Preference: Office > Permanent > anything;
	address_types restricts which addresses count."""
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
	if address_types:
		addresses = [a for a in addresses if a.address_type in address_types]
	if not addresses:
		return None

	preferred_order = ["Office", "Permanent", "Personal", "Billing", "Shipping"]
	addresses.sort(
		key=lambda a: preferred_order.index(a.address_type) if a.address_type in preferred_order else 99
	)
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

	branch, company = frappe.db.get_value("Employee", employee_name, ["branch", "company"]) or (None, None)

	state_text = None
	if branch:
		state_text = _address_state_via_dynamic_link("Branch", branch)
	if not state_text:
		state_text = _address_state_via_dynamic_link("Employee", employee_name, address_types=("Office",))
	if not state_text and company:
		state_text = _address_state_via_dynamic_link("Company", company)

	if state_text:
		code_map = _state_name_to_code_map()
		# Accept either the full name ("Karnataka") or the code ("KA").
		if state_text in code_map:
			return code_map[state_text]

	# Last resort — HR Settings default.
	default_state = _hr_setting_default_pt_state()
	if default_state:
		return default_state

	return None
