// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Shift Location", {
	refresh: (frm) => {
		// A Shift Location always stores its own coordinates and geofence radius.
		// Whether a check-in is geofenced is decided per Shift Type, not here.
		if (!frm.doc.__islocal)
			indian_hrms_compliance.add_shift_tools_button_to_form(frm, {
				action: "Assign Shift",
				shift_location: frm.doc.name,
			});
	},

	fetch_geolocation: (frm) => {
		indian_hrms_compliance.fetch_geolocation(frm);
	},
});
