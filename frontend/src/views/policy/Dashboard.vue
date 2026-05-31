<template>
	<BaseLayout :pageTitle="__('HR Policies')">
		<template #body>
			<div class="flex flex-col mt-7 mb-7 px-4 py-4 gap-5">
				<ion-segment v-model="activeTab" mode="md">
					<ion-segment-button value="pending">
						<ion-label>{{ __("Pending") }}</ion-label>
					</ion-segment-button>
					<ion-segment-button value="acknowledged">
						<ion-label>{{ __("Acknowledged") }}</ion-label>
					</ion-segment-button>
				</ion-segment>

				<div v-if="activeTab === 'pending'" class="flex flex-col gap-3">
					<PolicyCard
						v-for="policy in pendingPolicies.data"
						:key="policy.name"
						:policy="policy"
					/>
					<EmptyState
						v-if="!pendingPolicies.data?.length"
						:message="__('No policies pending acknowledgement')"
					/>
				</div>

				<div v-else class="flex flex-col gap-3">
					<PolicyCard
						v-for="policy in acknowledgedPolicies.data"
						:key="policy.name"
						:policy="policy"
					/>
					<EmptyState
						v-if="!acknowledgedPolicies.data?.length"
						:message="__('No acknowledged policies yet')"
					/>
				</div>
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { ref } from "vue"
import { IonSegment, IonSegmentButton, IonLabel } from "@ionic/vue"

import BaseLayout from "@/components/BaseLayout.vue"
import EmptyState from "@/components/EmptyState.vue"
import PolicyCard from "@/components/PolicyCard.vue"

import { pendingPolicies, acknowledgedPolicies } from "@/data/policies"

const activeTab = ref("pending")
</script>
