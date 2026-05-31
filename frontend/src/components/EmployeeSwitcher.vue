<template>
	<!-- Only render when the user has more than one active employment. -->
	<div v-if="hasMultiple">
		<button
			class="flex flex-row items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 active:bg-gray-200"
			@click="openSheet = true"
		>
			<FeatherIcon name="briefcase" class="h-3.5 w-3.5 text-gray-600" />
			<span class="max-w-[7rem] truncate text-xs font-medium text-gray-700">
				{{ currentCompany }}
			</span>
			<FeatherIcon name="chevron-down" class="h-3.5 w-3.5 text-gray-500" />
		</button>

		<ion-action-sheet
			:is-open="openSheet"
			:header="__('Switch Employer')"
			:buttons="actionButtons"
			@didDismiss="openSheet = false"
		></ion-action-sheet>
	</div>
</template>

<script setup>
import { computed, inject, ref, onMounted } from "vue"
import { FeatherIcon } from "frappe-ui"
import { IonActionSheet } from "@ionic/vue"

import { myEmployees, setActiveEmployee } from "@/data/employees"

const __ = inject("$translate")
const employee = inject("$employee")

const openSheet = ref(false)

onMounted(() => {
	// Lazy-load the employment list only when the switcher could be shown.
	if (employee?.data?.has_multiple_employments && !myEmployees.data) {
		myEmployees.reload()
	}
})

const hasMultiple = computed(() => !!employee?.data?.has_multiple_employments)

const currentCompany = computed(() => employee?.data?.company || "")

const actionButtons = computed(() => {
	const list = (myEmployees.data || []).map((emp) => {
		const isCurrent = emp.name === employee?.data?.name
		return {
			text: `${emp.company}${isCurrent ? "  ✓" : ""}`,
			handler: () => {
				if (!isCurrent) setActiveEmployee(emp.name)
			},
		}
	})
	list.push({ text: __("Cancel"), role: "cancel" })
	return list
})
</script>
