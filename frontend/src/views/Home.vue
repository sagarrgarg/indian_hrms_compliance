<template>
	<BaseLayout>
		<template #body>
			<div class="min-h-full bg-gray-50">
				<div class="flex flex-col my-5 p-4 gap-4">
					<CheckInPanel />

					<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
						<TaskCalendar :tasks="tasks" />
						<PreviewList
							:title="__('My Tasks')"
							:items="taskItems"
							:empty="__('No pending tasks 🎉')"
							:more-to="{ name: 'TasksDashboard' }"
						/>
					</div>

					<QuickLinks :items="quickLinks" :title="__('Quick Links')" />
					<RequestPanel />
				</div>
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { computed, inject, markRaw } from "vue"

import CheckInPanel from "@/components/CheckInPanel.vue"
import QuickLinks from "@/components/QuickLinks.vue"
import BaseLayout from "@/components/BaseLayout.vue"
import RequestPanel from "@/components/RequestPanel.vue"
import TaskCalendar from "@/components/home/TaskCalendar.vue"
import PreviewList from "@/components/home/PreviewList.vue"
import { myTasks } from "@/data/tasks"
import AttendanceIcon from "@/components/icons/AttendanceIcon.vue"
import ShiftIcon from "@/components/icons/ShiftIcon.vue"
import ExpenseIcon from "@/components/icons/ExpenseIcon.vue"
import SalaryIcon from "@/components/icons/SalaryIcon.vue"
import PolicyIcon from "@/components/icons/PolicyIcon.vue"
import TaskIcon from "@/components/icons/TaskIcon.vue"
import GrievanceIcon from "@/components/icons/GrievanceIcon.vue"
import POSHIcon from "@/components/icons/POSHIcon.vue"
import ApprovalsIcon from "@/components/icons/ApprovalsIcon.vue"
import CockpitIcon from "@/components/icons/CockpitIcon.vue"
import { canViewCockpit } from "@/data/cockpit"

const __ = inject("$translate")

// Day-to-day actions only. Privacy/Consent, Resignation & Exit, Leave and
// Advance live under Profile (deliberate — not daily, and not nudges).
const allLinks = [
	{
		icon: markRaw(CockpitIcon),
		title: __("HR Cockpit"),
		route: "Cockpit",
		color: "indigo",
		hrOnly: true,
	},
	{
		icon: markRaw(ApprovalsIcon),
		title: __("Approvals"),
		route: "ApprovalsInbox",
		color: "amber",
	},
	{
		icon: markRaw(AttendanceIcon),
		title: __("Request Attendance"),
		route: "AttendanceRequestFormView",
		color: "sky",
	},
	{
		icon: markRaw(ShiftIcon),
		title: __("Request a Shift"),
		route: "ShiftRequestFormView",
		color: "violet",
	},
	{
		icon: markRaw(ExpenseIcon),
		title: __("Claim an Expense"),
		route: "ExpenseClaimFormView",
		color: "orange",
	},
	{
		icon: markRaw(SalaryIcon),
		title: __("View Salary Slips"),
		route: "SalarySlipsDashboard",
		color: "blue",
	},
	{
		icon: markRaw(TaskIcon),
		title: __("My Tasks"),
		route: "TasksDashboard",
		color: "fuchsia",
	},
	{
		icon: markRaw(PolicyIcon),
		title: __("HR Policies"),
		route: "PoliciesDashboard",
		color: "cyan",
	},
	{
		icon: markRaw(GrievanceIcon),
		title: __("Grievances"),
		route: "GrievancesDashboard",
		color: "purple",
	},
	{
		icon: markRaw(POSHIcon),
		title: __("POSH Complaint"),
		route: "POSHDashboard",
		color: "pink",
	},
]

const quickLinks = computed(() => allLinks.filter((l) => !l.hrOnly || canViewCockpit.data))

// --- Dashboard previews ---
const todayStr = new Date().toISOString().slice(0, 10)
const tasks = computed(() => myTasks.data || [])

const taskItems = computed(() =>
	tasks.value
		.filter((t) => ["Pending", "In Progress"].includes(t.status))
		.sort((a, b) => String(a.due_date || "").localeCompare(String(b.due_date || "")))
		.map((t) => {
			const overdue = t.due_date && String(t.due_date).slice(0, 10) < todayStr
			return {
				title: t.goal_name || t.name,
				subtitle: t.due_date ? __("Due {0}", [t.due_date]) : "",
				tone: overdue ? "red" : "indigo",
				badge: overdue ? __("Overdue") : t.status,
				to: { name: "TaskDetailView", params: { id: t.name } },
			}
		}),
)
</script>
