<template>
	<BaseLayout :pageTitle="__('My Tasks')">
		<template #body>
			<div class="flex flex-col mt-7 mb-7 px-4 py-4 gap-5">
				<div class="grid grid-cols-3 gap-3">
					<div class="flex flex-col gap-1 bg-white rounded p-3 items-center">
						<span class="text-2xl font-bold text-gray-900">
							{{ myTaskSummary.data?.due_today ?? 0 }}
						</span>
						<span class="text-xs text-gray-500 text-center">
							{{ __("Due Today") }}
						</span>
					</div>
					<div class="flex flex-col gap-1 bg-white rounded p-3 items-center">
						<span class="text-2xl font-bold text-red-600">
							{{ myTaskSummary.data?.overdue ?? 0 }}
						</span>
						<span class="text-xs text-gray-500 text-center">
							{{ __("Overdue") }}
						</span>
					</div>
					<div class="flex flex-col gap-1 bg-white rounded p-3 items-center">
						<span class="text-2xl font-bold text-green-600">
							{{ myTaskSummary.data?.completed_this_week ?? 0 }}
						</span>
						<span class="text-xs text-gray-500 text-center">
							{{ __("Done This Week") }}
						</span>
					</div>
				</div>

				<ion-segment v-model="activeTab" mode="md" scrollable>
					<ion-segment-button value="today">
						<ion-label>{{ __("Today") }}</ion-label>
					</ion-segment-button>
					<ion-segment-button value="overdue">
						<ion-label>{{ __("Overdue") }}</ion-label>
					</ion-segment-button>
					<ion-segment-button value="upcoming">
						<ion-label>{{ __("Upcoming") }}</ion-label>
					</ion-segment-button>
					<ion-segment-button value="completed">
						<ion-label>{{ __("Completed") }}</ion-label>
					</ion-segment-button>
				</ion-segment>

				<div class="flex flex-col gap-3">
					<TaskCard
						v-for="task in tasks.data"
						:key="task.name"
						:task="task"
					/>
					<EmptyState
						v-if="!tasks.loading && !tasks.data?.length"
						:message="__('No tasks here')"
					/>
				</div>
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { ref, watch } from "vue"
import { IonSegment, IonSegmentButton, IonLabel } from "@ionic/vue"

import BaseLayout from "@/components/BaseLayout.vue"
import EmptyState from "@/components/EmptyState.vue"
import TaskCard from "@/components/TaskCard.vue"

import { myTaskSummary, myTasks as tasks } from "@/data/tasks"

const activeTab = ref("today")

function reloadForTab(tab) {
	tasks.update({ params: { period: tab } })
	tasks.reload()
}

watch(activeTab, reloadForTab, { immediate: true })
</script>
