import { createResource, call } from "frappe-ui"

// The department(s) the logged-in user heads, with members and re-point rights.
export const myDepartment = createResource({
	url: "indian_hrms_compliance.overrides.org_tree.get_my_department",
	auto: true,
	cache: "indian_hrms_compliance:my_department",
})

// Head-only re-point of a member's reporting line. Never grants Employee write —
// the server endpoint enforces the head-boundary guards.
export async function setReportsTo(employee, newManager) {
	const r = await call("indian_hrms_compliance.overrides.org_tree.set_reports_to", {
		employee,
		new_manager: newManager || "",
	})
	myDepartment.reload()
	return r
}
