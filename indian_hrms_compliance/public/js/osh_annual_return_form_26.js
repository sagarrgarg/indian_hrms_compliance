// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("OSH Annual Return Form 26", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.filing_status !== "Filed") {
			frm.add_custom_button(__("Generate Form 26"), () => {
				frappe
					.call({
						method:
							"indian_hrms_compliance.overrides.osh_form_26_generator.generate_osh_form_26",
						args: { form_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Generating Form 26..."),
					})
					.then((r) => {
						if (r.message) {
							const exceptions = r.message.exceptions || [];
							let msg = `<b>Total Workers:</b> ${r.message.total_workers}<br>`;
							msg += `<b>Average Daily Workers:</b> ${r.message.average_daily_workers}<br>`;
							msg += `<b>Status:</b> ${r.message.filing_status}<br>`;
							if (exceptions.length) {
								msg +=
									"<br><b>Exceptions:</b><br>" + exceptions.join("<br>");
							}
							frappe.msgprint({
								title: __("Form 26 Generated"),
								indicator: exceptions.length ? "orange" : "green",
								message: msg,
							});
							frm.reload_doc();
						}
					});
			});
		}
		if (frm.doc.filing_status === "Generated") {
			frm.dashboard.add_indicator(__("Generated — pending filing"), "blue");
		}
		if (frm.doc.filing_status === "Filed") {
			frm.dashboard.add_indicator(__("Filed"), "green");
		}
	},
	total_workers_male: (frm) => recompute_total(frm),
	total_workers_female: (frm) => recompute_total(frm),
	total_workers_others: (frm) => recompute_total(frm),
});

function recompute_total(frm) {
	const total =
		(frm.doc.total_workers_male || 0) +
		(frm.doc.total_workers_female || 0) +
		(frm.doc.total_workers_others || 0);
	frm.set_value("total_workers", total);
}
