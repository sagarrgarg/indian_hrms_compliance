<template>
	<BaseLayout :pageTitle="__('My Profile Updates')" back>
		<template #body>
			<div class="flex flex-col mt-5 mb-7 px-4 py-2 gap-4">
				<!-- Action: submit a new request -->
				<button
					class="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-indigo-600 text-white text-sm font-medium active:scale-[0.99]"
					@click="$router.push({ name: 'EditProfile' })"
				>
					<FeatherIcon name="plus" class="h-4 w-4" />
					{{ __("Request a new update") }}
				</button>

				<EmptyState
					v-if="myProfileChangeRequests.loading && !myProfileChangeRequests.data"
					:message="__('Loading...')"
				/>

				<EmptyState
					v-else-if="!(myProfileChangeRequests.data || []).length"
					:message="__('No profile updates yet. Tap above to request one.')"
				/>

				<!-- History -->
				<div
					v-for="r in myProfileChangeRequests.data || []"
					:key="r.name"
					class="bg-white rounded-xl border border-gray-100 p-4 flex flex-col gap-2"
				>
					<div class="flex items-center justify-between">
						<div class="text-sm font-semibold text-gray-900">{{ r.name }}</div>
						<span :class="['text-xs px-2 py-0.5 rounded-full font-medium', statusClass(r.status)]">
							{{ __(r.status) }}
						</span>
					</div>
					<div class="text-xs text-gray-500">
						{{ __("Submitted") }} {{ fmt(r.submitted_at) }} · {{ __("{0} field(s)", [r.change_count]) }}
					</div>
					<div v-if="r.reviewed_at" class="text-xs text-gray-500">
						{{ __("Reviewed") }} {{ fmt(r.reviewed_at) }}
						<span v-if="r.reviewed_by"> · {{ r.reviewed_by }}</span>
					</div>
					<div v-if="r.review_notes" class="text-xs text-gray-700 bg-gray-50 rounded p-2 mt-1">
						<span class="font-semibold">{{ __("HR note:") }}</span> {{ r.review_notes }}
					</div>

					<div v-if="r.status === 'Submitted'" class="flex gap-2 mt-1">
						<Button
							variant="outline"
							theme="red"
							size="sm"
							class="text-xs"
							:loading="withdrawingId === r.name"
							@click="onWithdraw(r.name)"
						>
							{{ __("Withdraw") }}
						</Button>
					</div>
				</div>
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { inject, onBeforeUnmount, onMounted, ref } from "vue"
import { Button, FeatherIcon, toast } from "frappe-ui"

import BaseLayout from "@/components/BaseLayout.vue"
import EmptyState from "@/components/EmptyState.vue"

import { myProfileChangeRequests, withdrawProfileChange } from "@/data/profileChange"

const __ = inject("$translate")
const socket = inject("$socket")

const withdrawingId = ref("")

function fmt(s) {
	if (!s) return ""
	try {
		const d = new Date(String(s).replace(" ", "T"))
		if (isNaN(d.getTime())) return s
		return d.toLocaleString([], {
			year: "numeric",
			month: "short",
			day: "numeric",
			hour: "2-digit",
			minute: "2-digit",
		})
	} catch {
		return s
	}
}

function statusClass(status) {
	return (
		{
			Submitted: "bg-orange-50 text-orange-700",
			Approved: "bg-green-50 text-green-700",
			Rejected: "bg-red-50 text-red-700",
			Withdrawn: "bg-gray-100 text-gray-600",
		}[status] || "bg-gray-100 text-gray-600"
	)
}

function onWithdraw(name) {
	withdrawingId.value = name
	withdrawProfileChange.submit(
		{ name },
		{
			onSuccess() {
				toast({ title: __("Withdrawn"), icon: "check-circle", position: "bottom-center" })
				myProfileChangeRequests.reload()
			},
			onError(error) {
				toast({
					title: __("Error"),
					text: error?.messages?.[0] || error.message,
					icon: "alert-circle",
					position: "bottom-center",
					iconClasses: "text-red-500",
				})
			},
			onComplete() {
				withdrawingId.value = ""
			},
		}
	)
}

// Layer-2 live refresh: HR approve/reject lands as a list_update on this doctype.
function onListUpdate(d) {
	if (d?.doctype === "Employee Profile Change Request") myProfileChangeRequests.reload()
}
onMounted(() => {
	socket.emit("doctype_subscribe", "Employee Profile Change Request")
	socket.on("list_update", onListUpdate)
})
onBeforeUnmount(() => {
	socket.emit("doctype_unsubscribe", "Employee Profile Change Request")
	socket.off("list_update", onListUpdate)
})
</script>
