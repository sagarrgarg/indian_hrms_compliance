# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from indian_hrms_compliance.overrides.resignation_request_workflow import (
	setup_resignation_request_workflow,
)


def execute():
	"""Install the default Resignation Request Approval workflow."""
	setup_resignation_request_workflow()
