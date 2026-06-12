import { createResource } from "frappe-ui"

// One resource, two modes — the `for_date` arg drives the today-vs-past path
// on the server. cache key stays stable so socket.js refetches hit the same
// resource regardless of the date being viewed.
export const orgAttendanceToday = createResource({
	url: "indian_hrms_compliance.api.get_org_attendance_today",
	auto: true,
	cache: "indian_hrms_compliance:org_attendance_today",
})
