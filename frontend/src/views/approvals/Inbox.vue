<template>
	<BaseLayout :pageTitle="__('Approvals')">
		<template #body>
			<div class="flex flex-col mt-7 mb-7 px-4 py-4 gap-5">
				<div class="flex flex-col gap-1 bg-white rounded p-4 items-center">
					<span class="text-3xl font-bold text-gray-900">
						{{ approvalsSummary.data?.total ?? 0 }}
					</span>
					<span class="text-xs text-gray-500 text-center">
						{{ __("Pending Approvals") }}
					</span>
				</div>

				<ion-segment v-model="activeTab" mode="md" scrollable>
					<ion-segment-button value="All">
						<ion-label>{{ __("All") }}</ion-label>
					</ion-segment-button>
					<ion-segment-button
						v-for="cat in categories"
						:key="cat"
						:value="cat"
					>
						<ion-label>{{ __(cat) }}</ion-label>
					</ion-segment-button>
				</ion-segment>

				<div class="flex flex-col gap-3">
					<ApprovalCard
						v-for="item in filteredItems"
						:key="`${item.doctype}:${item.name}`"
						:item="item"
						@actioned="reload"
					/>
					<EmptyState
						v-if="!pendingApprovals.loading && !filteredItems.length"
						:message="__('You\'re all caught up')"
					/>
				</div>
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { ref, computed } from "vue"
import { IonSegment, IonSegmentButton, IonLabel } from "@ionic/vue"

import BaseLayout from "@/components/BaseLayout.vue"
import EmptyState from "@/components/EmptyState.vue"
import ApprovalCard from "@/components/ApprovalCard.vue"

import { pendingApprovals, approvalsSummary } from "@/data/approvals"

const activeTab = ref("All")

const categories = ["Leave", "Expense", "Advance", "Shift", "Attendance", "Task", "Resignation"]

const filteredItems = computed(() => {
	const items = pendingApprovals.data || []
	if (activeTab.value === "All") return items
	return items.filter((i) => i.category === activeTab.value)
})

function reload() {
	pendingApprovals.reload()
	approvalsSummary.reload()
}
</script>
