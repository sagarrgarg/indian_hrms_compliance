<template>
	<router-link
		:to="{
			name: 'ConsentNoticeView',
			params: { purposeCode: consent.purpose_code },
		}"
		v-slot="{ navigate }"
	>
		<div
			class="flex flex-row items-center justify-between bg-white rounded p-4 cursor-pointer"
			@click="navigate"
		>
			<div class="flex flex-col gap-1.5 grow">
				<div class="text-base font-medium text-gray-800">
					{{ consent.purpose_name }}
				</div>
				<div class="flex flex-row items-center gap-2 flex-wrap">
					<ion-badge color="medium">{{ consent.lawful_basis }}</ion-badge>
					<span
						v-if="consent.consent_status === 'Active' && consent.granted_on"
						class="text-xs text-gray-500"
					>
						{{ __("Granted") }}
						{{ dayjs(consent.granted_on).format("D MMM YYYY") }}
					</span>
				</div>
			</div>
			<div class="flex flex-row items-center gap-2 ml-2">
				<ion-badge :color="statusColor">{{ statusLabel }}</ion-badge>
				<FeatherIcon name="chevron-right" class="h-5 w-5 text-gray-400" />
			</div>
		</div>
	</router-link>
</template>

<script setup>
import { inject, computed } from "vue"
import { IonBadge } from "@ionic/vue"
import { FeatherIcon } from "frappe-ui"

const __ = inject("$translate")
const dayjs = inject("$dayjs")

const props = defineProps({
	consent: {
		type: Object,
		required: true,
	},
})

const statusColor = computed(() => {
	switch (props.consent.consent_status) {
		case "Active":
			return "success"
		case "Withdrawn":
			return "medium"
		default:
			return "warning"
	}
})

const statusLabel = computed(() => __(props.consent.consent_status))
</script>
