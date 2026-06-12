import { computed, reactive } from "vue"
import { createResource, call } from "frappe-ui"
import { userResource } from "./user"
import { employeeResource } from "./employee"
import router from "@/router"

export function sessionUser() {
	let cookies = new URLSearchParams(document.cookie.split("; ").join("&"))
	let _sessionUser = cookies.get("user_id")
	if (_sessionUser === "Guest") {
		_sessionUser = null
	}
	return _sessionUser
}

function handleLogin(response) {
	if (response.message === "Logged In") {
		userResource.reload()
		employeeResource.reload()

		session.user = sessionUser()
		router.replace({ path: "/" })
	}
}

export const session = reactive({
	login: async (email, password) => {
		const response = await call("login", { usr: email, pwd: password })
		handleLogin(response)
		return response
	},
	otp: async (tmp_id, otp) => {
		const response = await call("login", { tmp_id, otp })
		handleLogin(response)
		return response
	},
	logout: createResource({
		url: "logout",
		async onSuccess() {
			// In the native shell, unhook this device from the site's push so the
			// user stops getting this company's notifications after logout.
			try {
				const { teardownNativePush } = await import("@/composables/useNativePush")
				await teardownNativePush()
			} catch (e) {
				/* best-effort */
			}

			userResource.reset()
			employeeResource.reset()

			session.user = sessionUser()
			router.replace({ name: "Login" })
			window.location.reload()
		},
	}),
	user: sessionUser(),
	isLoggedIn: computed(() => !!session.user),
})
