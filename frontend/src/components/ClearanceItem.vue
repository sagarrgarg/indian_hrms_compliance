<template>
	<div class="flex flex-row items-center justify-between bg-white rounded p-4">
		<div class="flex flex-col gap-1 grow">
			<div class="flex flex-row items-center gap-2">
				<span class="text-base font-medium text-gray-800">
					{{ item.clearance_area }}
				</span>
				<ion-badge v-if="item.blocking" color="danger" class="text-xs">
					{{ __("Blocking") }}
				</ion-badge>
			</div>
			<div v-if="item.description" class="text-xs text-gray-500">
				{{ item.description }}
			</div>
			<div v-if="item.clearance_owner" class="text-xs text-gray-400">
				{{ __("Owner") }}: {{ item.clearance_owner }}
			</div>
		</div>
		<ion-badge :color="statusColor" class="ml-2">
			{{ item.status }}
		</ion-badge>
	</div>
</template>

<script setup>
import { inject, computed } from "vue"
import { IonBadge } from "@ionic/vue"

const __ = inject("$translate")

const props = defineProps({
	item: {
		type: Object,
		required: true,
	},
})

const statusColor = computed(() => {
	switch (props.item.status) {
		case "Cleared":
			return "success"
		case "Held":
			return "danger"
		default:
			return "warning"
	}
})
</script>
