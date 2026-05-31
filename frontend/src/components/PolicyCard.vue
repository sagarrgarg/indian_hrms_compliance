<template>
	<router-link
		:to="{ name: 'PolicyAcknowledgeView', params: { id: policy.name } }"
		v-slot="{ navigate }"
	>
		<div
			class="flex flex-row items-center justify-between bg-white rounded p-4 cursor-pointer"
			@click="navigate"
		>
			<div class="flex flex-col gap-1.5 grow">
				<div class="text-base font-medium text-gray-800">
					{{ policy.policy_name_fetched || policy.policy }}
				</div>
				<div class="flex flex-row items-center gap-2 flex-wrap">
					<ion-badge color="medium">{{ policy.policy_category }}</ion-badge>
					<span class="text-xs text-gray-500">
						{{ __("Version") }} {{ policy.policy_version }}
					</span>
				</div>
				<div
					v-if="policy.status === 'Pending' && policy.due_date"
					class="text-xs text-gray-500"
				>
					{{ __("Due") }} {{ dayjs(policy.due_date).format("D MMM YYYY") }}
				</div>
				<div
					v-else-if="policy.status === 'Acknowledged' && policy.acknowledged_at"
					class="text-xs text-gray-500"
				>
					{{ __("Acknowledged") }}
					{{ dayjs(policy.acknowledged_at).format("D MMM YYYY") }}
				</div>
			</div>
			<div class="flex flex-row items-center gap-2 ml-2">
				<ion-badge :color="policy.status === 'Acknowledged' ? 'success' : 'warning'">
					{{ policy.status }}
				</ion-badge>
				<FeatherIcon name="chevron-right" class="h-5 w-5 text-gray-400" />
			</div>
		</div>
	</router-link>
</template>

<script setup>
import { inject } from "vue"
import { IonBadge } from "@ionic/vue"
import { FeatherIcon } from "frappe-ui"

const dayjs = inject("$dayjs")

defineProps({
	policy: {
		type: Object,
		required: true,
	},
})
</script>
