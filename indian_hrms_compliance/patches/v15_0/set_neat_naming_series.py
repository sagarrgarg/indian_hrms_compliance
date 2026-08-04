# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Short, fiscal-year-based naming for Salary Slip and Journal Entry.

Relies on the .FY. naming token registered via the naming_series_variables hook.
Payroll Entry naming (PE-{abbr}-{FY}-####) is handled in its controller autoname.

  - Salary Slip  -> SS-{emp code}-{FY}-##   (e.g. SS-GGIL-003-2026-2027-01)
  - Journal Entry-> JV{FY}-####  system-wide (e.g. JV2026-2027-0001)

Existing documents keep their names; only new ones use the new series. Runs
once; safe to re-run (make_property_setter upserts).
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
	# Salary Slip.autoname defers to a custom-autoname Property Setter (see the
	# controller's has_custom_naming_series), so this is the supported override.
	make_property_setter(
		"Salary Slip",
		None,
		"autoname",
		"SS-.employee.-.FY.-.##.",
		"Data",
		for_doctype=True,
		validate_fields_for_doctype=False,
	)

	# Journal Entry uses a naming_series field: make JV{FY}-#### the sole option so
	# every new Journal Entry (payroll, payments, manual) defaults to it.
	make_property_setter(
		"Journal Entry",
		"naming_series",
		"options",
		"JV.FY.-.####.",
		"Text",
		validate_fields_for_doctype=False,
	)
	make_property_setter(
		"Journal Entry",
		"naming_series",
		"default",
		"JV.FY.-.####.",
		"Data",
		validate_fields_for_doctype=False,
	)

	frappe.clear_cache(doctype="Salary Slip")
	frappe.clear_cache(doctype="Journal Entry")
