import { createResource } from "frappe-ui"

export const myPOSHComplaints = createResource({
	url: "indian_hrms_compliance.api.get_my_posh_complaints",
	auto: true,
	cache: "indian_hrms_compliance:my_posh_complaints",
})

export const poshHelpInfo = createResource({
	url: "indian_hrms_compliance.api.get_posh_help_info",
	auto: true,
	cache: "indian_hrms_compliance:posh_help_info",
})

export const poshComplaintDetail = createResource({
	url: "indian_hrms_compliance.api.get_posh_complaint_detail",
})

export const filePOSHComplaint = createResource({
	url: "indian_hrms_compliance.api.file_posh_complaint",
})
