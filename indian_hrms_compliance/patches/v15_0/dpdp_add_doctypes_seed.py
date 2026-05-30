# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Phase 6D — reload the 6 new DPDP doctypes after install.

`bench migrate` will sync new JSON doctypes automatically, but on a
fresh install we still want to be defensive — if any of these
reload_doc calls fails, the entire 6D feature breaks silently.
"""

import frappe


DPDP_DOCTYPES = [
	("hr", "data_consent_purpose"),
	("hr", "data_consent"),
	("hr", "data_access_log"),
	("hr", "data_retention_rule"),
	("hr", "data_erasure_request"),
	("hr", "dpdp_compliance_profile"),
]


def execute():
	for module, doctype in DPDP_DOCTYPES:
		try:
			frappe.reload_doc(module, "doctype", doctype, force=True)
		except Exception as e:
			print(f"  WARN: reload_doc {doctype} failed: {e}")
	print(f"  Phase 6D: reloaded {len(DPDP_DOCTYPES)} DPDP doctypes")
