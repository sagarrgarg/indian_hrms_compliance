import { createResource } from "frappe-ui"

export const myResignationStatus = createResource({
	url: "indian_hrms_compliance.api.get_my_resignation_status",
	auto: true,
	cache: "indian_hrms_compliance:my_resignation_status",
})

export const resignationFormDefaults = createResource({
	url: "indian_hrms_compliance.api.get_resignation_form_defaults",
	cache: "indian_hrms_compliance:resignation_form_defaults",
})

export const submitResignationRequest = createResource({
	url: "indian_hrms_compliance.api.submit_resignation_request",
})

export const withdrawResignationRequest = createResource({
	url: "indian_hrms_compliance.api.withdraw_resignation_request",
})

export const myExitClearance = createResource({
	url: "indian_hrms_compliance.api.get_my_exit_clearance",
	auto: true,
	cache: "indian_hrms_compliance:my_exit_clearance",
})

export const myExitDocuments = createResource({
	url: "indian_hrms_compliance.api.get_my_exit_documents",
	auto: true,
	cache: "indian_hrms_compliance:my_exit_documents",
})
