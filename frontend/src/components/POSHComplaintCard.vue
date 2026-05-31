<template>
	<router-link
		:to="{ name: 'POSHDetailView', params: { id: complaint.name } }"
		v-slot="{ navigate }"
	>
		<div
			class="flex flex-row items-center justify-between bg-white rounded p-4 cursor-pointer"
			@click="navigate"
		>
			<div class="flex flex-col gap-1.5 grow">
				<div class="flex flex-row items-center gap-2">
					<span class="text-base font-medium text-gray-800">
						{{ __("Complaint") }}
					</span>
					<ion-badge v-if="complaint.anonymous" color="medium">
						{{ __("Anonymous") }}
					</ion-badge>
				</div>
				<div v-if="complaint.filing_date" class="text-xs text-gray-500">
					{{ __("Filed") }}
					{{ dayjs(complaint.filing_date).format("D MMM YYYY") }}
				</div>
				<div v-if="complaint.sla_due_date" class="text-xs text-gray-500">
					{{ __("90-day SLA due") }}
					{{ dayjs(complaint.sla_due_date).format("D MMM YYYY") }}
				</div>
			</div>
			<div class="flex flex-row items-center gap-2 ml-2">
				<ion-badge :color="stateColor">
					{{ complaint.workflow_state }}
				</ion-badge>
				<FeatherIcon name="chevron-right" class="h-5 w-5 text-gray-400" />
			</div>
		</div>
	</router-link>
</template>

<script setup>
import { inject, computed } from "vue"
import { IonBadge } from "@ionic/vue"
import { FeatherIcon } from "frappe-ui"

const dayjs = inject("$dayjs")

const props = defineProps({
	complaint: {
		type: Object,
		required: true,
	},
})

const stateColor = computed(() => {
	switch (props.complaint.workflow_state) {
		case "Closed":
			return "success"
		case "Filed":
			return "danger"
		default:
			return "warning"
	}
})
</script>
