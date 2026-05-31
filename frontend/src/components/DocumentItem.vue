<template>
	<a
		:href="href"
		target="_blank"
		rel="noopener"
		class="flex flex-row items-center justify-between bg-white rounded p-4"
	>
		<div class="flex flex-col gap-1 grow">
			<div class="text-base font-medium text-gray-800">
				{{ title }}
			</div>
			<div v-if="subtitle" class="text-xs text-gray-500">
				{{ subtitle }}
			</div>
		</div>
		<FeatherIcon name="download" class="h-5 w-5 text-blue-600 ml-2" />
	</a>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"

defineProps({
	title: {
		type: String,
		required: true,
	},
	subtitle: {
		type: String,
		required: false,
		default: "",
	},
	href: {
		type: String,
		required: true,
	},
})
</script>
