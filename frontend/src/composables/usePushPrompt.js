import { alertController } from "@ionic/vue"

import { arePushNotificationsEnabled } from "@/data/notifications"
import { isNativeApp } from "@/composables/useNativePush"

const DISMISS_KEY = "ihc-push-prompt-dismissed-until"
// Re-ask after this many days if the user tapped "Maybe later".
const REASK_DAYS = 7

function dismissedRecently() {
	const until = window.localStorage.getItem(DISMISS_KEY)
	if (!until) return false
	const ts = parseInt(until, 10)
	return !isNaN(ts) && Date.now() < ts
}

function snooze() {
	window.localStorage.setItem(DISMISS_KEY, String(Date.now() + REASK_DAYS * 24 * 60 * 60 * 1000))
}

/**
 * Decide whether to ask, and if so show a SOFT prompt. Tapping "Enable" is what
 * triggers the real OS permission dialog — never fire it unprompted, because
 * iOS only lets you ask once per install and a reflex "Don't Allow" is permanent.
 *
 * Call this after login lands on Home. Safe to call repeatedly — it self-gates.
 *
 * @param {(text: string) => string} translate - the $translate fn
 */
export async function maybePromptForPush(translate) {
	const __ = translate || ((s) => s)

	// Gate 0: inside the native Kaam shell, push is handled natively (see
	// useNativePush). The native OS permission prompt is shown there — don't
	// also show the web soft-prompt.
	if (isNativeApp()) return

	const pn = window.frappePushNotification

	// Gate 1: push plumbing must exist on this build.
	if (!pn) return

	// Gate 2: push must be configured + enabled on the SITE.
	if (!window.frappe?.boot?.push_relay_server_url) return
	if (!arePushNotificationsEnabled.data) {
		// The resource may not have resolved yet on first paint — give it a beat.
		try {
			await arePushNotificationsEnabled.reload()
		} catch (e) {
			return
		}
		if (!arePushNotificationsEnabled.data) return
	}

	// Gate 3: already enabled on THIS device → nothing to do.
	if (pn.isNotificationEnabled()) return

	// Gate 4: the device/browser must actually support it (HTTPS + SW + FCM).
	try {
		const { isSupported } = await import("firebase/messaging")
		if (!(await isSupported())) return
	} catch (e) {
		return
	}

	// Gate 5: user snoozed it recently.
	if (dismissedRecently()) return

	const alert = await alertController.create({
		header: __("Stay updated"),
		message: __(
			"Turn on notifications to get instant alerts for approvals, tasks, and important HR updates — even when the app is closed."
		),
		backdropDismiss: false,
		buttons: [
			{
				text: __("Maybe later"),
				role: "cancel",
				handler: () => {
					snooze()
				},
			},
			{
				text: __("Enable"),
				role: "confirm",
				handler: () => {
					// Fire-and-forget; the OS prompt appears next. Errors are
					// swallowed so a denied permission doesn't surface a scary toast
					// during onboarding.
					pn.enableNotification().catch(() => {})
				},
			},
		],
	})
	await alert.present()
}
