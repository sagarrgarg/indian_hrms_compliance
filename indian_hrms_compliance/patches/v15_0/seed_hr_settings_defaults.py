# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe


HR_SETTINGS_DEFAULTS = {
	# Performance & Tasks tab
	"task_scheduler_lookahead_days": 1,
	"auto_archive_completed_task_instances_after_days": 90,
	"show_overdue_task_popup_on_login": 1,
	"send_overdue_task_hr_digest": 1,
	"task_overdue_recipients_role": "HR Manager",
	"task_compliance_warning_threshold_pct": 80,
	"task_compliance_critical_threshold_pct": 50,
	"appraisal_auto_populate_kra_performance": 1,
	# Policies & Acknowledgements tab
	"default_policy_ack_due_days": 7,
	"show_overdue_policy_popup_on_login": 1,
	"send_overdue_policy_hr_digest": 1,
	"policy_overdue_recipients_role": "HR Manager",
	# Probation & Confirmation tab
	"default_probation_period_days": 180,
	"probation_review_reminder_window_days": 30,
}


def execute():
	"""Seed HR Settings (Single) with sensible defaults for the new
	Performance & Tasks / Policies / Probation settings tabs.

	JSON `default:` only fires when a row is freshly inserted — the
	HR Settings Single row predates these fields, so the columns came in as
	NULL / 0. This patch writes the intended defaults once so HR opens the
	form to populated values. HR is free to override afterwards via the UI.
	"""
	for field, default_value in HR_SETTINGS_DEFAULTS.items():
		frappe.db.set_single_value("HR Settings", field, default_value)
	print(f"  HR Settings: seeded {len(HR_SETTINGS_DEFAULTS)} default values")
