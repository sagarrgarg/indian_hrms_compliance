/**
 * Native push notifications for when the HRMS PWA runs inside the Kaam
 * Capacitor shell (github: kaam-mobile).
 *
 * Why this lives in the PWA, not the wrapper:
 *   - The Capacitor runtime bridge (`window.Capacitor`) is injected into the
 *     remote pages too (the wrapper's capacitor.config sets allowNavigation),
 *     so the HRMS PWA can call native plugins directly.
 *   - The token must be registered against THIS site using the logged-in
 *     session — which only the WebView (this app) has.
 *
 * We talk to the plugin via the runtime bridge
 * (`window.Capacitor.Plugins.FirebaseMessaging`) rather than an ES import, so
 * the PWA build never has to depend on the native plugin package. The plugin
 * is installed in the kaam-mobile project; here we just use it if present.
 *
 * On the web (normal browser PWA) every function below no-ops — web push is
 * handled separately by FrappePushNotification / usePushPrompt.
 */

import { call } from "frappe-ui"

// Must match the project the relay is keyed on (see pwa_notification.py).
const PROJECT_NAME = "hrms"

export function isNativeApp() {
	return !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform())
}

function messagingPlugin() {
	// @capacitor-firebase/messaging registers under this name.
	return window.Capacitor?.Plugins?.FirebaseMessaging || null
}

async function registerToken(token) {
	if (!token) return
	try {
		await call("frappe.push_notification.subscribe", {
			fcm_token: token,
			project_name: PROJECT_NAME,
		})
	} catch (e) {
		// Never block the app on a push-subscribe failure.
		console.warn("[native-push] subscribe failed", e?.message || e)
	}
}

/**
 * Request permission, register for FCM, push the token to this site, and wire
 * tap-to-navigate. Safe to call repeatedly and on the web (no-ops there).
 *
 * @param {import('vue-router').Router} [router] - to deep-link on notification tap
 * @returns {Promise<boolean>} true if native push was set up
 */
export async function setupNativePush(router) {
	if (!isNativeApp()) return false
	const FM = messagingPlugin()
	if (!FM) {
		// Wrapper build doesn't include the Firebase Messaging plugin yet.
		console.info("[native-push] FirebaseMessaging plugin not present — skipping")
		return false
	}

	try {
		const perm = await FM.requestPermissions()
		if (perm?.receive !== "granted") {
			console.info("[native-push] permission not granted:", perm?.receive)
			return false
		}

		// Token refresh — re-register whenever FCM rotates the token.
		await FM.addListener("tokenReceived", (event) => registerToken(event?.token))

		// Tap on a notification → deep-link into the matching screen.
		await FM.addListener("notificationActionPerformed", (event) => {
			const route = event?.notification?.data?.route
			if (route && router) {
				router.push(route).catch(() => {})
			}
		})

		const { token } = await FM.getToken()
		if (token) await registerToken(token)
		return true
	} catch (e) {
		console.error("[native-push] setup failed", e)
		return false
	}
}

/**
 * Unsubscribe the current device token from THIS site and drop it locally.
 * Call on logout / before switching sites so the user stops getting this
 * company's notifications. No-ops on the web.
 */
export async function teardownNativePush() {
	if (!isNativeApp()) return
	const FM = messagingPlugin()
	if (!FM) return
	try {
		const { token } = await FM.getToken()
		if (token) {
			try {
				await call("frappe.push_notification.unsubscribe", {
					fcm_token: token,
					project_name: PROJECT_NAME,
				})
			} catch (e) {
				/* best-effort */
			}
		}
		await FM.deleteToken()
	} catch (e) {
		console.warn("[native-push] teardown failed", e?.message || e)
	}
}
