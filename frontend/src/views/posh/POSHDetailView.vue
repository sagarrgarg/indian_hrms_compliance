<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="w-full sm:w-96">
				<div
					class="flex flex-row bg-white shadow-sm py-4 px-3 items-center border-b"
				>
					<Button
						variant="ghost"
						class="!px-1 mr-1 hover:bg-white"
						@click="router.back()"
					>
						<FeatherIcon name="chevron-left" class="h-5 w-5" />
					</Button>
					<h2 class="text-xl font-semibold text-gray-900 truncate">
						{{ __("Complaint") }}
					</h2>
				</div>
			</div>
		</ion-header>

		<ion-content class="ion-no-padding">
			<div class="flex flex-col h-full w-screen sm:w-96">
				<div v-if="detail" class="flex flex-col gap-5 p-4 pb-28">
					<!-- Confidentiality reassurance -->
					<div
						class="flex flex-row gap-3 rounded p-4 border-l-4"
						style="background: #fdecea; border-color: #d33"
					>
						<FeatherIcon
							name="shield"
							class="h-5 w-5 shrink-0 mt-0.5 text-red-700"
						/>
						<div class="text-xs text-red-700 leading-relaxed">
							{{
								__(
									"Only you, the Internal Committee, and the respondent can see this complaint. It is handled in strict confidence."
								)
							}}
						</div>
					</div>

					<!-- Status stepper -->
					<div class="flex flex-col gap-3 bg-white rounded p-4">
						<div class="text-sm font-semibold text-gray-700">
							{{ __("Status") }}
						</div>
						<div class="flex flex-col gap-0">
							<div
								v-for="(step, idx) in steps"
								:key="step"
								class="flex flex-row items-start gap-3"
							>
								<div class="flex flex-col items-center">
									<div
										class="w-5 h-5 rounded-full flex items-center justify-center text-white text-xs"
										:class="
											idx <= currentStep
												? 'bg-green-500'
												: 'bg-gray-300'
										"
									>
										<FeatherIcon
											v-if="idx < currentStep"
											name="check"
											class="h-3 w-3"
										/>
									</div>
									<div
										v-if="idx < steps.length - 1"
										class="w-0.5 h-6"
										:class="
											idx < currentStep
												? 'bg-green-500'
												: 'bg-gray-200'
										"
									></div>
								</div>
								<span
									class="text-sm pb-3"
									:class="
										idx === currentStep
											? 'font-semibold text-gray-900'
											: 'text-gray-500'
									"
								>
									{{ step }}
								</span>
							</div>
						</div>
					</div>

					<!-- Details -->
					<div class="flex flex-col gap-3 bg-white rounded p-4">
						<div class="flex flex-row justify-between">
							<span class="text-sm text-gray-500">{{ __("Filed") }}</span>
							<span class="text-sm font-medium text-gray-800">
								{{ dayjs(detail.filing_date).format("D MMM YYYY") }}
							</span>
						</div>
						<div
							v-if="detail.sla_due_date"
							class="flex flex-row justify-between"
						>
							<span class="text-sm text-gray-500">
								{{ __("90-day SLA due") }}
							</span>
							<span class="text-sm font-medium text-gray-800">
								{{ dayjs(detail.sla_due_date).format("D MMM YYYY") }}
							</span>
						</div>
						<div
							v-if="detail.incident_date"
							class="flex flex-row justify-between"
						>
							<span class="text-sm text-gray-500">
								{{ __("Incident Date") }}
							</span>
							<span class="text-sm font-medium text-gray-800">
								{{ dayjs(detail.incident_date).format("D MMM YYYY") }}
							</span>
						</div>
						<div
							v-if="detail.incident_location"
							class="flex flex-row justify-between"
						>
							<span class="text-sm text-gray-500">
								{{ __("Location") }}
							</span>
							<span class="text-sm font-medium text-gray-800">
								{{ detail.incident_location }}
							</span>
						</div>
					</div>

					<div
						v-if="detail.incident_description"
						class="flex flex-col gap-2 bg-white rounded p-4"
					>
						<div class="text-sm font-semibold text-gray-700">
							{{ __("Incident Summary") }}
						</div>
						<div class="text-sm text-gray-700 leading-relaxed whitespace-pre-line">
							{{ detail.incident_description }}
						</div>
					</div>
				</div>

				<EmptyState
					v-else-if="poshComplaintDetail.error"
					:message="__('This complaint is not available')"
				/>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { inject, computed, watch } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonHeader, IonContent } from "@ionic/vue"
import { Button, FeatherIcon } from "frappe-ui"

import EmptyState from "@/components/EmptyState.vue"
import { poshComplaintDetail } from "@/data/posh"

const props = defineProps({
	id: {
		type: String,
		required: true,
	},
})

const __ = inject("$translate")
const dayjs = inject("$dayjs")
const router = useRouter()

poshComplaintDetail.submit({ name: props.id })

watch(
	() => props.id,
	(id) => {
		if (id) poshComplaintDetail.submit({ name: id })
	}
)

const detail = computed(() => poshComplaintDetail.data)

const steps = computed(
	() =>
		detail.value?.steps || [
			"Filed",
			"Acknowledged",
			"Inquiry",
			"Findings Recorded",
			"Action Recommended",
			"Closed",
		]
)

const currentStep = computed(() => {
	const idx = steps.value.indexOf(detail.value?.workflow_state)
	return idx === -1 ? 0 : idx
})
</script>
