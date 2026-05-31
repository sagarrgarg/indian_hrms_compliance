<template>
	<div class="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
		<div class="flex items-center justify-between mb-2">
			<h3 class="text-sm font-semibold text-gray-800">{{ title }}</h3>
			<router-link v-if="moreTo" :to="moreTo" class="text-xs text-indigo-600 font-medium">
				{{ __("View all") }}
			</router-link>
		</div>

		<p v-if="!items.length" class="text-sm text-gray-400 py-3 text-center">{{ empty || __("Nothing here") }}</p>

		<ul v-else class="flex flex-col divide-y divide-gray-50">
			<li v-for="(item, i) in items.slice(0, max)" :key="i">
				<button class="w-full flex items-center gap-3 py-2.5 text-left active:scale-[0.99] transition" @click="open(item)">
					<span :class="['mt-0.5 h-2 w-2 rounded-full shrink-0', dot(item.tone)]" />
					<span class="flex-1 min-w-0">
						<span class="block text-sm text-gray-800 truncate">{{ item.title }}</span>
						<span v-if="item.subtitle" class="block text-xs text-gray-400 truncate">{{ item.subtitle }}</span>
					</span>
					<span v-if="item.badge" :class="['text-[10px] font-semibold px-2 py-0.5 rounded-full', badge(item.tone)]">
						{{ item.badge }}
					</span>
					<FeatherIcon name="chevron-right" class="h-4 w-4 text-gray-300 shrink-0" />
				</button>
			</li>
		</ul>
	</div>
</template>

<script setup>
import { inject } from "vue"
import { useRouter } from "vue-router"
import { FeatherIcon } from "frappe-ui"

const __ = inject("$translate")
const router = useRouter()

defineProps({
	title: { type: String, required: true },
	items: { type: Array, default: () => [] },
	empty: { type: String, default: "" },
	moreTo: { type: [Object, String], default: null },
	max: { type: Number, default: 5 },
})

const DOT = { green: "bg-emerald-500", amber: "bg-amber-500", red: "bg-red-500", indigo: "bg-indigo-500", grey: "bg-gray-300" }
const BADGE = {
	green: "bg-emerald-50 text-emerald-600",
	amber: "bg-amber-50 text-amber-600",
	red: "bg-red-50 text-red-600",
	indigo: "bg-indigo-50 text-indigo-600",
	grey: "bg-gray-100 text-gray-500",
}
const dot = (t) => DOT[t] || DOT.grey
const badge = (t) => BADGE[t] || BADGE.grey

function open(item) {
	if (item.to) router.push(item.to).catch(() => {})
}
</script>
