import { createResource } from "frappe-ui"

export const myTaskSummary = createResource({
	url: "indian_hrms_compliance.api.get_my_task_summary",
	auto: true,
	cache: "indian_hrms_compliance:my_task_summary",
})

export const myTasks = createResource({
	url: "indian_hrms_compliance.api.get_my_task_instances",
	auto: true,
	cache: "indian_hrms_compliance:my_tasks",
})

export const completeTask = createResource({
	url: "indian_hrms_compliance.api.complete_task_instance",
})
