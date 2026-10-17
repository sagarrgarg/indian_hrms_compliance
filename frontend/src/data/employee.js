import router from "@/router"
import { createResource } from "frappe-ui"

export const employeeResource = createResource({
	url: "indian_hrms_compliance.api.get_current_employee_info",
	cache: "indian_hrms_compliance:employee",
	onError(error) {
		if (error && error.exc_type === "AuthenticationError") {
			router.push("/login")
		}
	},
})
