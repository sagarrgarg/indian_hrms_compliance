// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// Data Consent — "Withdraw Consent" action on Active records.
frappe.ui.form.on("Data Consent", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.consent_status !== "Active") return;
		frm.add_custom_button(
			__("Withdraw Consent"),
			() => {
				frappe.prompt(
					[
						{
							fieldname: "reason",
							label: __("Withdrawal Reason"),
							fieldtype: "Small Text",
							reqd: 1,
						},
					],
					(values) => {
						frappe.call({
							method: "indian_hrms_compliance.hr.doctype.data_consent.data_consent.withdraw_consent",
							args: { name: frm.doc.name, reason: values.reason },
							freeze: true,
							freeze_message: __("Withdrawing consent..."),
							callback: () => frm.reload_doc(),
						});
					},
					__("Withdraw Consent"),
					__("Withdraw")
				);
			},
			__("DPDP")
		);
	},
});
