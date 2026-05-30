# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Phase 6D — install the Data Erasure Request workflow."""

from indian_hrms_compliance.overrides.dpdp_erasure_workflow import (
	setup_data_erasure_workflow,
)


def execute():
	setup_data_erasure_workflow()
	print("  Phase 6D: Data Erasure Request workflow installed")
