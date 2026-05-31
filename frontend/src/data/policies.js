import { createResource } from "frappe-ui"

export const pendingPolicies = createResource({
	url: "indian_hrms_compliance.api.get_pending_policy_acknowledgements",
	auto: true,
	cache: "indian_hrms_compliance:pending_policies",
})

export const acknowledgedPolicies = createResource({
	url: "indian_hrms_compliance.api.get_acknowledged_policies",
	auto: true,
	cache: "indian_hrms_compliance:acknowledged_policies",
})

export const acknowledgePolicy = createResource({
	url: "indian_hrms_compliance.api.acknowledge_policy",
})
