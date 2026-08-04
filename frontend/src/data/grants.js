import { createResource } from "frappe-ui"

// Options for the "request a grant" form: grantable employees + earning components.
export const grantFormOptions = createResource({
	url: "indian_hrms_compliance.api.get_grant_form_options",
	auto: false,
})

// Raise an ad-hoc pay grant (Incentive / Retention Bonus / Additional Salary /
// grace days) and send it for approval.
export const requestGrant = createResource({
	url: "indian_hrms_compliance.api.request_additional_salary",
})
