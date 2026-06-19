"""Wire the employee-activation orchestration.

Adds the per-company onboarding defaults (Company) that drive
``employee_master.auto_assign_leave_policy_on_activation``. The opt-in toggle
itself is a standard field on the HR Settings doctype (hr_settings.json); the
legacy Custom Field that this patch used to create is dropped by
``promote_auto_leave_policy_to_standard_field``.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_fields():
	return {
		"Company": [
			{
				"fieldname": "employee_onboarding_defaults_section",
				"fieldtype": "Section Break",
				"label": "Employee Onboarding Defaults",
				"description": (
					"Defaults applied when a new employee of this company is activated. "
					"The Leave Policy is auto-assigned if enabled in HR Settings."
				),
				"insert_after": "default_payroll_payable_account",
			},
			{
				"fieldname": "default_leave_policy",
				"fieldtype": "Link",
				"label": "Default Leave Policy",
				"options": "Leave Policy",
				"insert_after": "employee_onboarding_defaults_section",
			},
			{
				"fieldname": "default_leave_period",
				"fieldtype": "Link",
				"label": "Default Leave Period",
				"options": "Leave Period",
				"insert_after": "default_leave_policy",
			},
			{
				"fieldname": "employee_onboarding_defaults_column",
				"fieldtype": "Column Break",
				"insert_after": "default_leave_period",
			},
			{
				"fieldname": "default_shift_type",
				"fieldtype": "Link",
				"label": "Default Shift",
				"options": "Shift Type",
				"insert_after": "employee_onboarding_defaults_column",
			},
			{
				"fieldname": "default_salary_structure",
				"fieldtype": "Link",
				"label": "Default Salary Structure",
				"options": "Salary Structure",
				"insert_after": "default_shift_type",
			},
		],
	}


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)
