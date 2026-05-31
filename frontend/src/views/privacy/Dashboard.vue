<template>
	<BaseLayout :pageTitle="__('Privacy & Consent')">
		<template #body>
			<div class="flex flex-col mt-7 mb-7 px-4 py-4 gap-6 pb-24">
				<!-- (a) Your Consents -->
				<div class="flex flex-col gap-3">
					<div class="text-base font-semibold text-gray-900">
						{{ __("Your Consents") }}
					</div>
					<div class="text-xs text-gray-500 leading-relaxed -mt-1">
						{{
							__(
								"Purposes for which the organisation processes your personal data. Tap a purpose to read the notice and grant or withdraw consent."
							)
						}}
					</div>
					<ConsentCard
						v-for="item in consentOverview.data"
						:key="item.purpose_code"
						:consent="item"
					/>
					<EmptyState
						v-if="!consentOverview.data?.length"
						:message="__('No data processing purposes are defined')"
					/>
				</div>

				<!-- (b) Data We Hold -->
				<div class="flex flex-col gap-3">
					<div class="text-base font-semibold text-gray-900">
						{{ __("Data We Hold") }}
					</div>
					<div class="flex flex-col gap-3 bg-white rounded p-4">
						<div
							v-for="(cat, idx) in dataSummary.data?.categories"
							:key="cat.category"
							class="flex flex-col gap-1"
							:class="
								idx < (dataSummary.data?.categories?.length || 0) - 1
									? 'border-b pb-3'
									: ''
							"
						>
							<div class="text-sm font-medium text-gray-800">
								{{ cat.category }}
							</div>
							<div class="text-xs text-gray-500">{{ cat.examples }}</div>
							<div class="flex flex-row items-center gap-2 flex-wrap mt-1">
								<ion-badge color="medium">{{ cat.lawful_basis }}</ion-badge>
								<span class="text-xs text-gray-500">
									{{ __("Retention") }}: {{ cat.retention }}
								</span>
							</div>
						</div>
						<EmptyState
							v-if="!dataSummary.data?.categories?.length"
							:message="__('No data categories to show')"
						/>
					</div>
				</div>

				<!-- (c) Your Rights -->
				<div class="flex flex-col gap-3">
					<div class="text-base font-semibold text-gray-900">
						{{ __("Your Rights") }}
					</div>
					<div class="flex flex-col gap-3 bg-white rounded p-4">
						<div class="text-sm text-gray-600 leading-relaxed">
							{{
								__(
									"Under the Digital Personal Data Protection Act, 2023 you have the right to access a summary of your personal data, request correction of inaccurate data, and request erasure of data the organisation no longer needs."
								)
							}}
						</div>
						<div
							v-if="dataSummary.data?.dpo_email"
							class="text-sm text-gray-700"
						>
							{{ __("Data Protection Officer") }}:
							<a
								:href="`mailto:${dataSummary.data.dpo_email}`"
								class="text-blue-600 font-medium"
							>
								{{ dataSummary.data.dpo_email }}
							</a>
						</div>
						<Button
							variant="solid"
							class="w-full py-5 text-base mt-1"
							@click="goToErasure"
						>
							{{ __("Request Data Erasure") }}
						</Button>
					</div>
				</div>
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { inject } from "vue"
import { useRouter } from "vue-router"
import { IonBadge } from "@ionic/vue"
import { Button } from "frappe-ui"

import BaseLayout from "@/components/BaseLayout.vue"
import EmptyState from "@/components/EmptyState.vue"
import ConsentCard from "@/components/ConsentCard.vue"

import { consentOverview, dataSummary } from "@/data/privacy"

const __ = inject("$translate")
const router = useRouter()

function goToErasure() {
	router.push({ name: "ErasureRequestForm" })
}
</script>
