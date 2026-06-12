import { alertController } from "@ionic/vue"

import { pendingPolicies } from "@/data/policies"

// A pending acknowledgement is "overdue" once its due_date is strictly before
// today (local date, YYYY-MM-DD compare — same convention the Tasks dashboard
// uses for overdue badges).
function isOverdue(p) {
	if (!p || !p.due_date) return false
	const today = new Date().toISOString().slice(0, 10)
	return String(p.due_date).slice(0, 10) < today
}

export function getOverduePolicies() {
	return (pendingPolicies.data || []).filter(isOverdue)
}

/**
 * On Home load, if the employee has ANY overdue policy acknowledgement, show a
 * non-dismissible alert whose only action takes them to the Policies dashboard.
 * This is the hard-stop tier of the escalating nudge (badge → banner → gate).
 *
 * Returns true if the gate was shown (so the caller can suppress the softer
 * push-permission prompt that session and not stack two dialogs).
 *
 * Safe to call repeatedly — it self-gates on the data.
 *
 * @param {(text: string, args?: any[]) => string} translate - the $translate fn
 * @param {import('vue-router').Router} router
 */
export async function maybeShowPolicyAckGate(translate, router) {
	const __ = translate || ((s) => s)

	// The resource auto-fetches on import but may not have resolved on first
	// paint — give it one chance to load before deciding.
	if (!pendingPolicies.data) {
		try {
			await pendingPolicies.reload()
		} catch (e) {
			return false
		}
	}

	const overdue = getOverduePolicies()
	if (!overdue.length) return false

	const n = overdue.length
	const message =
		n === 1
			? __(
					"A mandatory HR policy acknowledgement is overdue. Please review and acknowledge it to continue."
			  )
			: __(
					"{0} mandatory HR policy acknowledgements are overdue. Please review and acknowledge them to continue.",
					[n]
			  )

	const alert = await alertController.create({
		header: __("Action required"),
		message,
		backdropDismiss: false,
		buttons: [
			{
				text: __("Review now"),
				role: "confirm",
				handler: () => {
					router.push({ name: "PoliciesDashboard" })
				},
			},
		],
	})
	await alert.present()
	return true
}
