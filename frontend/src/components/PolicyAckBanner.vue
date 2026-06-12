<template>
	<div
		v-if="visible"
		class="flex flex-row items-center gap-3 rounded-2xl border p-4 shadow-sm"
		:class="overdue ? 'bg-red-50 border-red-100' : 'bg-amber-50 border-amber-100'"
	>
		<span
			class="flex items-center justify-center h-10 w-10 rounded-xl shrink-0"
			:class="overdue ? 'bg-red-100 text-red-600' : 'bg-amber-100 text-amber-600'"
		>
			<FeatherIcon name="alert-triangle" class="h-5 w-5" />
		</span>
		<div class="flex flex-col grow min-w-0">
			<div class="text-sm font-semibold text-gray-900 leading-tight">
				{{ headline }}
			</div>
			<div class="text-xs text-gray-600 mt-0.5">
				{{ __("Tap Review to read and acknowledge.") }}
			</div>
		</div>
		<button
			class="shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium text-white transition active:scale-95"
			:class="overdue ? 'bg-red-600' : 'bg-amber-600'"
			@click="goToPolicies"
		>
			{{ __("Review") }}
		</button>
		<button
			class="shrink-0 p-1.5 text-gray-400 hover:text-gray-600"
			:aria-label="__('Dismiss')"
			@click="dismiss"
		>
			<FeatherIcon name="x" class="h-4 w-4" />
		</button>
	</div>
</template>

<script setup>
import { computed, inject, ref } from "vue"

import { useRouter } from "vue-router"

import { FeatherIcon } from "frappe-ui"

const __ = inject("$translate")
const router = useRouter()

const props = defineProps({
	// Total pending acknowledgements (drives whether the banner shows at all).
	count: { type: Number, default: 0 },
	// How many of those are past due (drives the red/amber treatment + copy).
	overdueCount: { type: Number, default: 0 },
})

// Snooze for the rest of the calendar day only — re-surfaces tomorrow while the
// acknowledgement is still pending. The hard-stop gate (overdue) is separate and
// is NOT snoozable.
const DISMISS_KEY = "ihc-policy-ack-banner-dismissed-on"

function todayStr() {
	return new Date().toISOString().slice(0, 10)
}

const dismissedToday = ref(window.localStorage.getItem(DISMISS_KEY) === todayStr())

const overdue = computed(() => props.overdueCount > 0)

const visible = computed(() => props.count > 0 && !dismissedToday.value)

const headline = computed(() => {
	if (props.overdueCount > 0) {
		return props.overdueCount === 1
			? __("1 HR policy acknowledgement is overdue")
			: __("{0} HR policy acknowledgements are overdue", [props.overdueCount])
	}
	return props.count === 1
		? __("1 HR policy is awaiting your acknowledgement")
		: __("{0} HR policies are awaiting your acknowledgement", [props.count])
})

function goToPolicies() {
	router.push({ name: "PoliciesDashboard" })
}

function dismiss() {
	window.localStorage.setItem(DISMISS_KEY, todayStr())
	dismissedToday.value = true
}
</script>
