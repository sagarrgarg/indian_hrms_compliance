import { io } from "socket.io-client"

import { getCachedListResource } from "frappe-ui/src/resources/listResource"
import { getCachedResource } from "frappe-ui/src/resources/resources"

// Lightweight diagnostics — `localStorage.setItem("ihc-socket-debug", "1")`
// in the browser console flips this on without a rebuild.
const DEBUG = typeof window !== "undefined" && window.localStorage?.getItem("ihc-socket-debug") === "1"
const log = (...a) => DEBUG && console.log("[ihc-socket]", ...a)

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
		// PWAs get backgrounded (tab inactive, screen off, mobile sleep). The
		// default of 5 attempts means a stale tab silently stops receiving live
		// updates. Reconnect indefinitely with a back-off so a returning tab
		// catches up automatically.
		reconnection: true,
		reconnectionAttempts: Infinity,
		reconnectionDelay: 1000,
		reconnectionDelayMax: 10000,
		randomizationFactor: 0.5,
	})

	socket.on("connect", () => log("connected", socket.id))
	socket.on("disconnect", (reason) => log("disconnected:", reason))
	socket.on("reconnect_attempt", (n) => log("reconnect_attempt", n))
	socket.on("connect_error", (e) => log("connect_error", e?.message || e))

	socket.on("indian_hrms_compliance:refetch_resource", (data) => {
		log("refetch_resource", data?.cache_key)
		if (!data?.cache_key) return
		const resource =
			getCachedResource(data.cache_key) || getCachedListResource(data.cache_key)
		if (resource) {
			resource.reload()
		} else {
			log("  …no cached resource registered under this key (no-op)")
		}
	})

	return socket
}
