import { createResource } from "frappe-ui"

export const myTaskSummary = createResource({
	url: "indian_hrms_compliance.api.get_my_task_summary",
	auto: true,
	cache: "indian_hrms_compliance:my_task_summary",
})

export const myTasks = createResource({
	url: "indian_hrms_compliance.api.get_my_task_instances",
	auto: true,
	cache: "indian_hrms_compliance:my_tasks",
})

// Single-call payload for the My Tasks PWA screen (5 partitioned buckets).
// Returns: { summary, today, adhoc, upcoming, overdue, completed_week }.
// KPI scorecard for the My Tasks screen — target vs actual, from the weekly
// KPI Snapshot rollup.
export const myScorecard = createResource({
	url: "indian_hrms_compliance.api.get_my_scorecard",
	auto: true,
	cache: "indian_hrms_compliance:my_scorecard",
})

export const myTasksDashboard = createResource({
	url: "indian_hrms_compliance.api.get_my_tasks_dashboard",
	auto: true,
	cache: "indian_hrms_compliance:my_tasks_dashboard",
})

export const completeTask = createResource({
	url: "indian_hrms_compliance.api.complete_task_instance",
})

export const reopenTask = createResource({
	url: "indian_hrms_compliance.api.reopen_task_instance",
})

export const myTeam = createResource({
	url: "indian_hrms_compliance.api.get_my_team",
	auto: true,
	cache: "indian_hrms_compliance:my_team",
})

export const createTeamTask = createResource({
	url: "indian_hrms_compliance.api.create_team_task",
})

// Head distribution: split an Accountable instance to reports; a report bounces
// a sub-task back to the head with a reason.
export const distributeTask = createResource({
	url: "indian_hrms_compliance.api.distribute_task",
})

export const bounceTask = createResource({
	url: "indian_hrms_compliance.api.bounce_task",
})

// Re-route a single OPEN instance: with to_employee → delegate it to one of the
// caller's direct reports; without → pull it back to the caller ("assign to me").
export const reassignTask = createResource({
	url: "indian_hrms_compliance.api.reassign_task_instance",
})
