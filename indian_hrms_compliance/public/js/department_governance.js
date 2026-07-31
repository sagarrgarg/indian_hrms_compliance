// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

// Filter the Headship pickers to the department's own ACTIVE employees, so a
// head / acting head can only be someone eligible. The controller enforces the
// same rule on save (active + same company); this stops you picking an invalid
// person in the first place instead of failing on save.

frappe.ui.form.on("Department", {
	refresh(frm) {
		const headQuery = () => {
			const filters = { status: "Active" };
			// Only constrain by company once it's set — a blank company shouldn't
			// filter everyone out.
			if (frm.doc.company) filters.company = frm.doc.company;
			return { filters };
		};
		["department_head", "acting_head"].forEach((f) => {
			if (frm.fields_dict[f]) frm.set_query(f, headQuery);
		});
	},

	company(frm) {
		// Changing the company should re-scope the pickers and clear a now-invalid
		// head rather than silently keep a cross-company one until save fails.
		["department_head", "acting_head"].forEach((f) => {
			const val = frm.doc[f];
			if (!val) return;
			frappe.db.get_value("Employee", val, "company").then((r) => {
				if (r?.message && frm.doc.company && r.message.company !== frm.doc.company) {
					frm.set_value(f, null);
				}
			});
		});
	},
});
