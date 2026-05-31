import { createResource } from "frappe-ui"

// Server-truth role check — PWA boot doesn't carry user.roles reliably.
export const canViewCockpit = createResource({
	url: "indian_hrms_compliance.api.cockpit.can_view_cockpit",
	auto: true,
	cache: "indian_hrms_compliance:can_view_cockpit",
})

export const cockpit = createResource({
	url: "indian_hrms_compliance.api.cockpit.get_hr_cockpit",
	params: { period: "Monthly" },
	auto: true,
	cache: "indian_hrms_compliance:hr_cockpit",
})

export function setCockpitPeriod(period) {
	cockpit.update({ params: { period } })
	return cockpit.reload()
}
