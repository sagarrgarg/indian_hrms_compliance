# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from indian_hrms_compliance.overrides.job_requisition_workflow import (
	setup_job_requisition_workflow,
)


def execute():
	"""Install the default Job Requisition Approval workflow on existing sites."""
	setup_job_requisition_workflow()
