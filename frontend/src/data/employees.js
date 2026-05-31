import { createResource, call } from "frappe-ui"
import { reactive } from "vue"
import { employeeResource } from "./employee"

let employeesByID = reactive({})
let employeesByUserID = reactive({})

// All Active Employee records linked to the logged-in user (multi-employment).
// Drives the company/employee switcher in the header.
export const myEmployees = createResource({
	url: "indian_hrms_compliance.api.get_my_employees",
	cache: "indian_hrms_compliance:my_employees",
	auto: false,
})

// Switch the active Employee context, then hard-reload so every employee-scoped
// resource (attendance, leave, claims, salary, etc.) re-fetches for the new
// employment. Switching employer is infrequent, so a full reload is the safest
// way to guarantee no stale per-employee state lingers.
export async function setActiveEmployee(employeeName) {
	await call("indian_hrms_compliance.api.set_active_employee", {
		employee: employeeName,
	})
	// Clear the cached single-employee context so it refetches on reload.
	employeeResource.reset()
	window.location.reload()
}

export const employees = createResource({
	url: "indian_hrms_compliance.api.get_all_employees",
	auto: true,
	transform(data) {
		return data.map((employee) => {
			employee.isActive = employee.status === "Active"
			employeesByID[employee.name] = employee
			employeesByUserID[employee.user_id] = employee

			return employee
		})
	},
	onError(error) {
		if (error && error.exc_type === "AuthenticationError") {
			router.push({ name: "Login" })
		}
	},
})

export function getEmployeeInfo(employeeID) {
	if (!employeeID) employeeID = employeeResource.data.name

	return employeesByID[employeeID]
}

export function getEmployeeInfoByUserID(userID) {
	return employeesByUserID[userID]
}
