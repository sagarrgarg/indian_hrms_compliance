import { createResource } from "frappe-ui"

export const myGrievances = createResource({
	url: "indian_hrms_compliance.api.get_my_grievances",
	auto: true,
	cache: "indian_hrms_compliance:my_grievances",
})

export const grievanceFormOptions = createResource({
	url: "indian_hrms_compliance.api.get_grievance_form_options",
	cache: "indian_hrms_compliance:grievance_form_options",
})

export const fileGrievance = createResource({
	url: "indian_hrms_compliance.api.file_grievance",
})
