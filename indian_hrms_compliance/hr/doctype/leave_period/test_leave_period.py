# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Employee", "Leave Type", "Leave Policy"]


class TestLeavePeriod(FrappeTestCase):
	pass


def create_leave_period(from_date, to_date):
	leave_period = frappe.db.get_value(
		"Leave Period",
		dict(
			from_date=from_date,
			to_date=to_date,
			is_active=1,
		),
		"name",
	)
	if leave_period:
		return frappe.get_doc("Leave Period", leave_period)

	leave_period = frappe.get_doc(
		{
			"doctype": "Leave Period",
			"from_date": from_date,
			"to_date": to_date,
			"is_active": 1,
		}
	).insert()
	return leave_period
