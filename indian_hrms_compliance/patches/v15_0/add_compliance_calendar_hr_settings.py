# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Add Phase 6C Compliance Calendar HR Settings fields.

Same Custom-Field-on-top-of-Statutory-tab approach as 6B-1 / 6B-2 to
avoid merge friction.

Fields added:
  compliance_calendar_upcoming_days              Int   default 7
  compliance_calendar_escalation_days_after_due  Int   default 3
  send_compliance_calendar_daily_digest          Check default 1
  compliance_calendar_digest_recipients_role     Link  Role default 'HR Manager'
  auto_link_filings_to_calendar                  Check default 1
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def get_fields():
	return {
		"HR Settings": [
			{
				"fieldname": "compliance_calendar_section_break",
				"fieldtype": "Section Break",
				"label": "Compliance Calendar",
				"insert_after": "responsible_person_default_designation",
				"collapsible": 1,
			},
			{
				"fieldname": "compliance_calendar_upcoming_days",
				"fieldtype": "Int",
				"label": "Compliance Calendar Upcoming Days",
				"insert_after": "compliance_calendar_section_break",
				"default": "7",
				"description": (
					"Days ahead of the due date to start nagging the responsible person about "
					"an upcoming compliance filing."
				),
			},
			{
				"fieldname": "compliance_calendar_escalation_days_after_due",
				"fieldtype": "Int",
				"label": "Compliance Calendar Escalation Days After Due",
				"insert_after": "compliance_calendar_upcoming_days",
				"default": "3",
				"description": (
					"Number of days past the due date after which to escalate to HR Manager."
				),
			},
			{
				"fieldname": "compliance_calendar_col_break",
				"fieldtype": "Column Break",
				"insert_after": "compliance_calendar_escalation_days_after_due",
			},
			{
				"fieldname": "send_compliance_calendar_daily_digest",
				"fieldtype": "Check",
				"label": "Send Compliance Calendar Daily Digest",
				"insert_after": "compliance_calendar_col_break",
				"default": "1",
				"description": (
					"Send a per-Company HTML digest email of upcoming + overdue filings to "
					"the HR Manager role each day."
				),
			},
			{
				"fieldname": "compliance_calendar_digest_recipients_role",
				"fieldtype": "Link",
				"options": "Role",
				"label": "Compliance Calendar Digest Recipients Role",
				"insert_after": "send_compliance_calendar_daily_digest",
				"default": "HR Manager",
				"description": "Role whose users receive the digest + escalation alerts.",
			},
			{
				"fieldname": "auto_link_filings_to_calendar",
				"fieldtype": "Check",
				"label": "Auto-link Filings to Calendar",
				"insert_after": "compliance_calendar_digest_recipients_role",
				"default": "1",
				"description": (
					"When a PF ECR / ESI / 24Q / PT / LWF / Form 16 / POSH Annual Report "
					"saves, automatically find + back-link its Compliance Filing row."
				),
			},
		],
	}


def execute():
	create_custom_fields(get_fields(), ignore_validate=True)
	print("  Added Phase 6C Compliance Calendar Custom Fields to HR Settings")
