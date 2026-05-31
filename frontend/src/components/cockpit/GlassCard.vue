<template>
	<div :class="['rounded-2xl p-4 sm:p-5', variantClass]">
		<div v-if="title || $slots.header" class="flex items-center justify-between mb-3">
			<h3 class="text-sm font-semibold tracking-wide text-gray-700 uppercase">
				{{ title }}
			</h3>
			<slot name="header" />
		</div>
		<slot />
	</div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	title: { type: String, default: "" },
	// "glass" — frosted accent (hero); "flat" — Material card for data zones.
	variant: { type: String, default: "flat" },
})

const variantClass = computed(() =>
	props.variant === "glass"
		? "bg-white border border-gray-100 shadow-md"
		: "bg-white border border-gray-100 shadow-sm",
)
</script>
