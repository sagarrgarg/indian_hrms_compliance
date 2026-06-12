import { createResource } from "frappe-ui"

const M = "indian_hrms_compliance.hr.doctype.employee_profile_change_request.employee_profile_change_request"

// Editable fields with their current value (sensitive ones masked) + label/type.
export const editableProfileFields = createResource({
	url: `${M}.get_my_profile_editable_fields`,
	auto: false,
	cache: "indian_hrms_compliance:editable_profile_fields",
})

// Submit a profile change request: { changes: [{fieldname, new_value}, ...], dpdp_consent: 1 }.
export const submitProfileChange = createResource({
	url: `${M}.submit_profile_change_request`,
})

// Employee-side withdraw of their own Submitted request.
export const withdrawProfileChange = createResource({
	url: `${M}.withdraw_profile_change_request`,
})

// History of the current employee's past profile change requests.
export const myProfileChangeRequests = createResource({
	url: `${M}.get_my_profile_change_requests`,
	auto: true,
	cache: "indian_hrms_compliance:my_profile_change_requests",
})
