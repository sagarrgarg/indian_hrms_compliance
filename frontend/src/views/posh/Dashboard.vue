<template>
	<BaseLayout :pageTitle="__('POSH Complaint')">
		<template #body>
			<div class="flex flex-col mt-7 mb-7 px-4 py-4 gap-5 pb-24">
				<!-- Confidentiality banner -->
				<div
					class="flex flex-row gap-3 rounded p-4 border-l-4"
					style="background: #fdecea; border-color: #d33"
				>
					<FeatherIcon
						name="shield"
						class="h-5 w-5 shrink-0 mt-0.5 text-red-700"
					/>
					<div class="flex flex-col gap-1">
						<div class="text-sm font-semibold text-red-800">
							{{ __("Strictly confidential") }}
						</div>
						<div class="text-xs text-red-700 leading-relaxed">
							{{
								__(
									"POSH complaints are confidential. Only you, the Internal Committee, and the respondent can access them — not HR or your manager."
								)
							}}
						</div>
					</div>
				</div>

				<!-- Statutory help -->
				<div
					v-if="help.help_text"
					class="text-xs text-gray-600 leading-relaxed bg-white rounded p-4"
				>
					{{ help.help_text }}
				</div>

				<!-- No active IC -->
				<div
					v-if="poshHelpInfo.data && !help.has_active_ic"
					class="flex flex-col gap-1 bg-white rounded p-4"
				>
					<div class="text-sm font-medium text-gray-800">
						{{ __("No Internal Committee available") }}
					</div>
					<div class="text-xs text-gray-500">
						{{
							__(
								"An Internal Committee has not been constituted for your company yet. Please contact HR before filing a complaint."
							)
						}}
					</div>
				</div>

				<!-- File a complaint -->
				<Button
					v-else-if="help.has_active_ic"
					variant="solid"
					class="w-full py-5 text-base"
					@click="goToNew"
				>
					{{ __("File a Complaint") }}
				</Button>

				<!-- My complaints -->
				<div class="flex flex-col gap-3">
					<div
						v-if="myPOSHComplaints.data?.length"
						class="text-base font-semibold text-gray-700"
					>
						{{ __("Your Complaints") }}
					</div>
					<POSHComplaintCard
						v-for="complaint in myPOSHComplaints.data"
						:key="complaint.name"
						:complaint="complaint"
					/>
					<EmptyState
						v-if="!myPOSHComplaints.data?.length"
						:message="__('You have not filed any complaints')"
					/>
				</div>
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { inject, computed } from "vue"
import { useRouter } from "vue-router"
import { Button, FeatherIcon } from "frappe-ui"

import BaseLayout from "@/components/BaseLayout.vue"
import EmptyState from "@/components/EmptyState.vue"
import POSHComplaintCard from "@/components/POSHComplaintCard.vue"

import { myPOSHComplaints, poshHelpInfo } from "@/data/posh"

const __ = inject("$translate")
const router = useRouter()

const help = computed(() => poshHelpInfo.data || {})

function goToNew() {
	router.push({ name: "POSHForm" })
}
</script>
