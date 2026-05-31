// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("HR Settings", {
	refresh: function (frm) {
		frm.set_query("sender", () => {
			return {
				filters: {
					enable_outgoing: 1,
				},
			};
		});
		frm.set_query("hiring_sender", () => {
			return {
				filters: {
					enable_outgoing: 1,
				},
			};
		});
	},

	apply_indian_statutory_defaults: function (frm) {
		frappe.confirm(
			__(
				"Re-apply all India-law-aligned HR defaults as of today? This is safe and idempotent.",
			),
			function () {
				frappe.call({
					method: "indian_hrms_compliance.hr.compliance_assistant.apply_indian_statutory_defaults",
					freeze: true,
					freeze_message: __("Applying Indian statutory defaults…"),
					callback: function (r) {
						if (!r.message) return;
						const failed = (r.message.results || []).filter((s) => !s.ok);
						frappe.show_alert({
							message: failed.length
								? __("Applied with {0} step(s) needing attention — see Error Log.", [
										failed.length,
									])
								: __("Indian statutory defaults applied (as of {0}).", [
										r.message.applied_on,
									]),
							indicator: failed.length ? "orange" : "green",
						});
						frm.reload_doc();
					},
				});
			},
		);
	},

	apply_recommended_policy_settings: function (frm) {
		frappe.confirm(
			__(
				"Set the recommended governance controls (approver mandatory, restrict back-dated leave, prevent self-approval, auto-assign leave policy) to ON?",
			),
			function () {
				frappe.call({
					method: "indian_hrms_compliance.hr.compliance_assistant.apply_recommended_policy_settings",
					freeze: true,
					freeze_message: __("Applying recommended policy settings…"),
					callback: function (r) {
						if (!r.message) return;
						frappe.show_alert({
							message: __("Recommended policy settings applied ({0} of {1} changed).", [
								(r.message.changed || []).length,
								r.message.total,
							]),
							indicator: "green",
						});
						frm.reload_doc();
					},
				});
			},
		);
	},

	run_ai_compliance_analysis: function (frm) {
		frappe.call({
			method: "indian_hrms_compliance.hr.compliance_assistant.run_ai_compliance_analysis",
			freeze: true,
			freeze_message: __("Researching & analysing compliance… this may take a minute."),
			callback: function (r) {
				if (!r.message) return;
				frappe.show_alert({
					message: __("AI analysis complete."),
					indicator: "green",
				});
				frm.reload_doc();
			},
		});
	},
});

frappe.tour["HR Settings"] = [
	{
		fieldname: "emp_created_by",
		title: "Employee Naming By",
		description: __(
			"Employee can be named by Employee ID if you assign one, or via Naming Series. Select your preference here.",
		),
	},
	{
		fieldname: "standard_working_hours",
		title: "Standard Working Hours",
		description: __(
			"Enter the Standard Working Hours for a normal work day. These hours will be used in calculations of reports such as Employee Hours Utilization and Project Profitability analysis.",
		),
	},
	{
		fieldname: "leave_and_expense_claim_settings",
		title: "Leave and Expense Claim Settings",
		description: __(
			"Review various other settings related to Employee Leaves and Expense Claim",
		),
	},
];
