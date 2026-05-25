import router from "@/router"
import { createResource } from "frappe-ui"

export const userResource = createResource({
	url: "indian_hrms_compliance.api.get_current_user_info",
	cache: "indian_hrms_compliance:user",
	onError(error) {
		if (error && error.exc_type === "AuthenticationError") {
			router.push({ name: "Login" })
		}
	},
})
