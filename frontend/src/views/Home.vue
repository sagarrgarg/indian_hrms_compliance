<template>
	<BaseLayout>
		<template #body>
			<div class="flex flex-col items-center my-7 p-4 gap-7">
				<CheckInPanel />
				<QuickLinks :items="quickLinks" :title="__('Quick Links')" />
				<RequestPanel />
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { inject, markRaw } from "vue"

import CheckInPanel from "@/components/CheckInPanel.vue"
import QuickLinks from "@/components/QuickLinks.vue"
import BaseLayout from "@/components/BaseLayout.vue"
import RequestPanel from "@/components/RequestPanel.vue"
import AttendanceIcon from "@/components/icons/AttendanceIcon.vue"
import ShiftIcon from "@/components/icons/ShiftIcon.vue"
import LeaveIcon from "@/components/icons/LeaveIcon.vue"
import ExpenseIcon from "@/components/icons/ExpenseIcon.vue"
import EmployeeAdvanceIcon from "@/components/icons/EmployeeAdvanceIcon.vue"
import SalaryIcon from "@/components/icons/SalaryIcon.vue"
import PolicyIcon from "@/components/icons/PolicyIcon.vue"
import TaskIcon from "@/components/icons/TaskIcon.vue"
import ExitIcon from "@/components/icons/ExitIcon.vue"
import GrievanceIcon from "@/components/icons/GrievanceIcon.vue"
import POSHIcon from "@/components/icons/POSHIcon.vue"
import PrivacyIcon from "@/components/icons/PrivacyIcon.vue"
import ApprovalsIcon from "@/components/icons/ApprovalsIcon.vue"

const __ = inject("$translate")

const quickLinks = [
	{
		icon: markRaw(AttendanceIcon),
		title: __("Request Attendance"),
		route: "AttendanceRequestFormView",
	},
	{
		icon: markRaw(ShiftIcon),
		title: __("Request a Shift"),
		route: "ShiftRequestFormView",
	},
	{
		icon: markRaw(LeaveIcon),
		title: __("Request Leave"),
		route: "LeaveApplicationFormView",
	},
	{
		icon: markRaw(ExpenseIcon),
		title: __("Claim an Expense"),
		route: "ExpenseClaimFormView",
	},
	{
		icon: markRaw(EmployeeAdvanceIcon),
		title: __("Request an Advance"),
		route: "EmployeeAdvanceFormView",
	},
	{
		icon: markRaw(SalaryIcon),
		title: __("View Salary Slips"),
		route: "SalarySlipsDashboard",
	},
	{
		icon: markRaw(PolicyIcon),
		title: __("HR Policies"),
		route: "PoliciesDashboard",
	},
	{
		icon: markRaw(TaskIcon),
		title: __("My Tasks"),
		route: "TasksDashboard",
	},
	{
		icon: markRaw(ExitIcon),
		title: __("Resignation & Exit"),
		route: "ExitDashboard",
	},
	{
		icon: markRaw(GrievanceIcon),
		title: __("Grievances"),
		route: "GrievancesDashboard",
	},
	{
		icon: markRaw(POSHIcon),
		title: __("POSH Complaint"),
		route: "POSHDashboard",
	},
	{
		icon: markRaw(PrivacyIcon),
		title: __("Privacy & Consent"),
		route: "PrivacyDashboard",
	},
	{
		icon: markRaw(ApprovalsIcon),
		title: __("Approvals"),
		route: "ApprovalsInbox",
	},
]
</script>
