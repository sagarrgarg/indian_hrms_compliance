import { createResource } from "frappe-ui"

export const orgGraph = createResource({
	url: "indian_hrms_compliance.api.org_graph.get_org_graph",
	auto: true,
	cache: "indian_hrms_compliance:org_graph",
})
