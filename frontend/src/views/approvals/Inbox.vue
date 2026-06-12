<template>
	<BaseLayout :pageTitle="__('Approvals')" back>
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
import { ref, computed, inject, onMounted, onBeforeUnmount } from "vue"
import { IonSegment, IonSegmentButton, IonLabel } from "@ionic/vue"

import BaseLayout from "@/components/BaseLayout.vue"
import EmptyState from "@/components/EmptyState.vue"
import ApprovalCard from "@/components/ApprovalCard.vue"

import { pendingApprovals, approvalsSummary } from "@/data/approvals"

const socket = inject("$socket")

const activeTab = ref("All")

const categories = [
	"Leave",
	"Expense",
	"Advance",
	"Shift",
	"Attendance",
	"Task",
	"Resignation",
	"Profile Update",
	"Onboarding",
	"Grievance",
]

// The 9 doctypes that can drop a row into the inbox. We subscribe to all so
// changes initiated outside the PWA (e.g., HR cancelling a Leave on the Desk)
// still trigger a refresh here — the backend's refetch_resource event covers
// PWA-initiated mutations, this list_update covers everything else.
const INBOX_DOCTYPES = [
	"Leave Application",
	"Expense Claim",
	"Employee Advance",
	"Shift Request",
	"Attendance Request",
	"Resignation Request",
	"Goal",
	"Employee Profile Change Request",
	"Employee Onboarding Application",
	"Employee Grievance",
]

const filteredItems = computed(() => {
	const items = pendingApprovals.data || []
	if (activeTab.value === "All") return items
	return items.filter((i) => i.category === activeTab.value)
})

function reload() {
	pendingApprovals.reload()
	approvalsSummary.reload()
}

function onListUpdate(data) {
	if (INBOX_DOCTYPES.includes(data?.doctype)) {
		reload()
	}
}

onMounted(() => {
	INBOX_DOCTYPES.forEach((dt) => socket.emit("doctype_subscribe", dt))
	socket.on("list_update", onListUpdate)
})

onBeforeUnmount(() => {
	INBOX_DOCTYPES.forEach((dt) => socket.emit("doctype_unsubscribe", dt))
	socket.off("list_update", onListUpdate)
})
</script>
