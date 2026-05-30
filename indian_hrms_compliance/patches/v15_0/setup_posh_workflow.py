# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from indian_hrms_compliance.overrides.posh_workflow import setup_posh_workflow


def execute():
	"""Install the default POSH Complaint Process workflow."""
	setup_posh_workflow()
