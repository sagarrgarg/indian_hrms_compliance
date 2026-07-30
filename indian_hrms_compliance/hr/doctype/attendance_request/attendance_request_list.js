// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.listview_settings["Attendance Request"] = {
	add_fields: ["status", "docstatus"],
	get_indicator(doc) {
		// The lifecycle status (custom field) takes precedence over docstatus.
		// Rejected / Needs-Clarification requests deliberately stay at
		// docstatus 0 (moved via db_set so validate() can't block the decision),
		// so without this they'd all show as "Draft" in the list.
		if (doc.docstatus === 2) return [__("Cancelled"), "gray", "docstatus,=,2"];
		if (doc.docstatus === 1) return [__("Approved"), "green", "docstatus,=,1"];
		switch (doc.status) {
			case "Rejected":
				return [__("Rejected"), "red", "status,=,Rejected"];
			case "Needs Clarification":
				return [__("Needs Clarification"), "blue", "status,=,Needs Clarification"];
			case "Open":
				return [__("Open"), "orange", "status,=,Open"];
			default:
				// Legacy rows from before the status field existed.
				return [__("Draft"), "gray", "docstatus,=,0"];
		}
	},
};
