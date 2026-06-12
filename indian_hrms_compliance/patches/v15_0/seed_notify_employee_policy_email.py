# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


def execute():
	"""Seed the new ``notify_employee_policy_email`` HR Setting to ON.

	The field ships with JSON default "1", but the HR Settings Single row
	predates it and DocType sync materialises a new Check column as 0, so the
	value never lands on the intended default on its own — and the gated email
	helper treats 0 as OFF. Write the default once (unconditionally — this is a
	brand-new toggle no HR user has configured yet) so employees actually get
	emailed on policy assignment / overdue. HR can untick it afterwards.
	"""
	frappe.db.set_single_value("HR Settings", "notify_employee_policy_email", 1)
	print("  HR Settings: seeded notify_employee_policy_email = 1")
