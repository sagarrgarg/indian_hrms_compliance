# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Phase 6E — install the Standing Orders Process workflow."""

from indian_hrms_compliance.overrides.standing_orders_workflow import (
	setup_standing_orders_workflow,
)


def execute():
	setup_standing_orders_workflow()
	print("  Installed Standing Orders Process workflow")
