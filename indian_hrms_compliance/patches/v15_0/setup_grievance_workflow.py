# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from indian_hrms_compliance.overrides.grievance_workflow import setup_grievance_workflow


def execute():
	"""Install the default Grievance Resolution workflow."""
	setup_grievance_workflow()
