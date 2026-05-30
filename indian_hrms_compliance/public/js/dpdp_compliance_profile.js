// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

// DPDP Compliance Profile — "Run SDF Readiness Check" button.
frappe.ui.form.on("DPDP Compliance Profile", {
	refresh(frm) {
		frm.add_custom_button(
			__("Run SDF Readiness Check"),
			() => {
				frappe.call({
					method: "indian_hrms_compliance.overrides.dpdp_sdf_checklist.get_sdf_readiness_report",
					freeze: true,
					freeze_message: __("Assessing SDF readiness..."),
					callback: (r) => {
						if (!r.message) return;
						const m = r.message;
						const status_row = (label, val, ok) => `
							<tr>
								<td style="padding:6px 12px">${label}</td>
								<td style="padding:6px 12px;color:${ok ? "#27ae60" : "#c0392b"};font-weight:600">
									${ok ? "✓" : "✗"} ${val}
								</td>
							</tr>
						`;
						const msg_html = (m.messages || []).map((x) =>
							`<li style="margin-bottom:4px">${frappe.utils.escape_html(x)}</li>`
						).join("");
						const score_color = m.risk_score >= 80 ? "#27ae60" :
						                    m.risk_score >= 50 ? "#f1c40f" : "#c0392b";
						const html = `
							<div>
								<div style="background:#f8f9fa;padding:14px 18px;margin-bottom:12px;border-left:4px solid ${score_color}">
									<strong>Readiness Score:</strong>
									<span style="font-size:24px;color:${score_color};font-weight:700;margin-left:8px">
										${m.risk_score}/100
									</span>
									<span style="margin-left:12px;color:#7f8c8d">
										(${m.is_designated_sdf ? "Designated SDF" : "Not Designated"})
									</span>
								</div>
								<table style="border-collapse:collapse;font-size:13px;margin-bottom:16px">
									${status_row(__("DPO Designated"), m.dpo_user || "—", m.dpo_designated)}
									${status_row(__("DPIA Current (≤12 months)"),
										m.dpia_months_since != null ? `${m.dpia_months_since} mo ago` : "never",
										m.dpia_current)}
									${status_row(__("Audit Current (≤12 months)"),
										m.audit_months_since != null ? `${m.audit_months_since} mo ago` : "never",
										m.audit_current)}
									${status_row(__("Consent Manager Integrated"),
										m.consent_managers_setup ? "yes" : "no",
										m.consent_managers_setup)}
									${status_row(__("Breach Process Documented"),
										m.breach_process_documented ? "yes" : "no",
										m.breach_process_documented)}
								</table>
								${msg_html ? `<h5>${__("Action Items")}</h5><ul>${msg_html}</ul>` : ""}
							</div>
						`;
						frappe.msgprint({
							title: __("SDF Readiness Report"),
							indicator: m.risk_score >= 80 ? "green" :
							           m.risk_score >= 50 ? "orange" : "red",
							message: html,
							wide: true,
						});
					},
				});
			},
			__("DPDP")
		);
	},
});
