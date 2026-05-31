import { createResource } from "frappe-ui"

const base = "indian_hrms_compliance.api.kra_tasks."

export const kraList = createResource({
	url: base + "list_kras",
	cache: "indian_hrms_compliance:kra_list",
})

export const hrmsTaskList = createResource({
	url: base + "list_hrms_tasks",
	cache: "indian_hrms_compliance:hrms_task_list",
})

export const formOptions = createResource({
	url: base + "get_form_options",
	cache: "indian_hrms_compliance:kra_task_options",
})

export const getKra = createResource({ url: base + "get_kra" })
export const saveKra = createResource({ url: base + "save_kra" })
export const deleteKra = createResource({ url: base + "delete_kra" })

export const getHrmsTask = createResource({ url: base + "get_hrms_task" })
export const saveHrmsTask = createResource({ url: base + "save_hrms_task" })
export const deleteHrmsTask = createResource({ url: base + "delete_hrms_task" })
