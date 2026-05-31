<template>
	<router-link
		:to="{ name: 'TaskDetailView', params: { id: task.name } }"
		v-slot="{ navigate }"
	>
		<div
			class="flex flex-row items-center justify-between bg-white rounded p-4 cursor-pointer"
			@click="navigate"
		>
			<div class="flex flex-col gap-1.5 grow">
				<div class="text-base font-medium text-gray-800">
					{{ task.goal_name }}
				</div>
				<div class="flex flex-row items-center gap-2 flex-wrap">
					<ion-badge v-if="task.kra" color="medium">{{ task.kra }}</ion-badge>
					<span v-if="task.period_label" class="text-xs text-gray-500">
						{{ task.period_label }}
					</span>
				</div>
				<div v-if="task.due_date" class="text-xs text-gray-500">
					{{ __("Due") }} {{ dayjs(task.due_date).format("D MMM YYYY") }}
				</div>
			</div>
			<div class="flex flex-row items-center gap-2 ml-2">
				<ion-badge :color="statusColor">{{ task.status }}</ion-badge>
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
	task: {
		type: Object,
		required: true,
	},
})

const statusColor = computed(() => {
	switch (props.task.status) {
		case "Completed":
			return "success"
		case "In Progress":
			return "primary"
		case "Archived":
		case "Closed":
			return "medium"
		default:
			return "warning"
	}
})
</script>
