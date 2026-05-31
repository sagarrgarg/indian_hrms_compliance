import { createResource } from "frappe-ui"

export const consentOverview = createResource({
	url: "indian_hrms_compliance.api.get_my_consent_overview",
	auto: true,
	cache: "indian_hrms_compliance:consent_overview",
})

export const dataSummary = createResource({
	url: "indian_hrms_compliance.api.get_my_data_summary",
	auto: true,
	cache: "indian_hrms_compliance:data_summary",
})

export const consentNotice = createResource({
	url: "indian_hrms_compliance.api.get_consent_notice",
})

export const grantConsent = createResource({
	url: "indian_hrms_compliance.api.grant_consent",
})

export const withdrawConsent = createResource({
	url: "indian_hrms_compliance.api.withdraw_consent",
})

export const myErasureRequests = createResource({
	url: "indian_hrms_compliance.api.get_my_erasure_requests",
	auto: true,
	cache: "indian_hrms_compliance:my_erasure_requests",
})

export const requestDataErasure = createResource({
	url: "indian_hrms_compliance.api.request_data_erasure",
})
