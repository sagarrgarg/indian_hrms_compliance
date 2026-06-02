<template>
	<BaseLayout :pageTitle="__('Grievances')" back>
		<template #body>
			<div class="flex flex-col mt-7 mb-7 px-4 py-4 gap-5 pb-24">
				<div class="flex flex-col gap-2 bg-white rounded p-5">
					<div class="text-sm text-gray-600 leading-relaxed">
						{{
							__(
								"Raise a workplace grievance and track its progress through manager and HR review. Your concern is routed to the right reviewer automatically."
							)
						}}
					</div>
					<Button
						variant="solid"
						class="w-full py-5 text-base mt-2"
						@click="goToNew"
					>
						{{ __("File a Grievance") }}
					</Button>
				</div>

				<div class="flex flex-col gap-3">
					<GrievanceCard
						v-for="grievance in myGrievances.data"
						:key="grievance.name"
						:grievance="grievance"
					/>
					<EmptyState
						v-if="!myGrievances.data?.length"
						:message="__('You have not raised any grievances yet')"
					/>
				</div>
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { inject } from "vue"
import { useRouter } from "vue-router"
import { Button } from "frappe-ui"

import BaseLayout from "@/components/BaseLayout.vue"
import EmptyState from "@/components/EmptyState.vue"
import GrievanceCard from "@/components/GrievanceCard.vue"

import { myGrievances } from "@/data/grievances"

const __ = inject("$translate")
const router = useRouter()

function goToNew() {
	router.push({ name: "GrievanceForm" })
}
</script>
