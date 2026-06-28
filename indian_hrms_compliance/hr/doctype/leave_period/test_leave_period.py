# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe

from indian_hrms_compliance.tests.utils import HRMSTestSuite


def create_leave_period(from_date, to_date, company=None):
	# Leave Period is global in indian_hrms_compliance (no company field); `company`
	# is accepted only for compatibility with upstream v16 test callers and ignored.
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
