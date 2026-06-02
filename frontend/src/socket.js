import { io } from "socket.io-client"

import { getCachedListResource } from "frappe-ui/src/resources/listResource"
import { getCachedResource } from "frappe-ui/src/resources/resources"

export function initSocket() {
	// Connect through the SAME origin/port that serves the app, not a hardcoded
	// socketio port. The reverse proxy (nginx) routes /socket.io to the realtime
	// server and injects the site header; hitting the raw socketio port directly
	// bypasses that and 400s. Works on whatever port/host the site runs on.
	const siteName = window.site_name
	const protocol = window.location.protocol === "https:" ? "https" : "http"
	const host = window.location.hostname
	const port = window.location.port ? `:${window.location.port}` : ""
	const url = `${protocol}://${host}${port}/${siteName}`
	let socket = io(url, {
		withCredentials: true,
		reconnectionAttempts: 5,
	})

	socket.on("indian_hrms_compliance:refetch_resource", (data) => {
		if (data.cache_key) {
			let resource =
				getCachedResource(data.cache_key) ||
				getCachedListResource(data.cache_key)

			if (resource) {
				resource.reload()
			}
		}
	})

	return socket
}
