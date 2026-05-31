"""Wire the employee-activation orchestration.

Adds the per-company onboarding defaults (Company) and the opt-in toggle
(HR Settings) that drive
``employee_master.auto_assign_leave_policy_on_activation``. Mirrors the
existing FnF auto-create pattern (per-feature defaults + a toggle + a hook).
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
		"HR Settings": [
			{
				"fieldname": "auto_assign_leave_policy_on_activation",
				"fieldtype": "Check",
				"label": "Auto-assign Leave Policy on Employee Activation",
				"insert_after": "prevent_self_leave_approval",
				"default": "0",
				"description": (
					"When ON, activating an employee auto-creates a Leave Policy "
					"Assignment from the company's Default Leave Policy / Leave Period "
					"(which cascades into Leave Allocations). Idempotent and opt-in."
				),
			},
		],
	}


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)
