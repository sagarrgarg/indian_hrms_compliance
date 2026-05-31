<template>
	<div class="flex flex-row items-center justify-between bg-white rounded p-4">
		<div class="flex flex-col gap-1.5 grow">
			<div class="text-base font-medium text-gray-800">
				{{ grievance.subject }}
			</div>
			<div class="flex flex-row items-center gap-2 flex-wrap">
				<ion-badge v-if="grievance.grievance_type" color="medium">
					{{ grievance.grievance_type }}
				</ion-badge>
				<ion-badge v-if="grievance.severity" :color="severityColor">
					{{ grievance.severity }}
				</ion-badge>
			</div>
			<div
				v-if="grievance.sla_due_date"
				class="text-xs text-gray-500"
			>
				{{ __("SLA due") }}
				{{ dayjs(grievance.sla_due_date).format("D MMM YYYY") }}
			</div>
		</div>
		<ion-badge :color="statusColor" class="ml-2">
			{{ grievance.workflow_state || grievance.status }}
		</ion-badge>
	</div>
</template>

<script setup>
import { inject, computed } from "vue"
import { IonBadge } from "@ionic/vue"

const __ = inject("$translate")
const dayjs = inject("$dayjs")

const props = defineProps({
	grievance: {
		type: Object,
		required: true,
	},
})

const severityColor = computed(() => {
	switch (props.grievance.severity) {
		case "Critical":
			return "danger"
		case "High":
			return "warning"
		case "Medium":
			return "primary"
		default:
			return "medium"
	}
})

const statusColor = computed(() => {
	switch (props.grievance.status) {
		case "Resolved":
			return "success"
		case "Invalid":
			return "danger"
		case "Open":
			return "warning"
		default:
			return "primary"
	}
})
</script>
