<template>
	<div class="flex flex-col gap-3 bg-white rounded p-4">
		<div class="flex flex-row items-start justify-between gap-2">
			<div class="flex flex-col gap-1 grow">
				<div class="text-base font-medium text-gray-800">
					{{ item.title }}
				</div>
				<div v-if="item.subtitle" class="text-sm text-gray-600">
					{{ item.subtitle }}
				</div>
				<div v-if="item.date" class="text-xs text-gray-500">
					{{ dayjs(item.date).format("D MMM YYYY") }}
				</div>
			</div>
			<ion-badge color="medium">{{ __(item.category) }}</ion-badge>
		</div>

		<div class="flex flex-row items-center gap-2">
			<EmployeeAvatar :employeeID="item.employee" />
			<div class="text-sm text-gray-600 grow">
				{{ item.employee_name || item.employee }}
			</div>
		</div>

		<div class="flex flex-row items-center justify-between gap-3 pt-1">
			<Button
				class="w-full py-4"
				variant="subtle"
				theme="red"
				:loading="busy"
				@click="onReject"
			>
				<template #prefix>
					<FeatherIcon name="x" class="w-4" />
				</template>
				{{ __("Reject") }}
			</Button>
			<Button
				class="w-full py-4"
				variant="solid"
				theme="green"
				:loading="busy"
				@click="onApprove"
			>
				<template #prefix>
					<FeatherIcon name="check" class="w-4" />
				</template>
				{{ __("Approve") }}
			</Button>
		</div>
	</div>
</template>

<script setup>
import { inject, ref } from "vue"
import { IonBadge, alertController } from "@ionic/vue"
import { toast, FeatherIcon, Button } from "frappe-ui"

import EmployeeAvatar from "@/components/EmployeeAvatar.vue"
import { approveRequest, rejectRequest } from "@/data/approvals"

const __ = inject("$translate")
const dayjs = inject("$dayjs")

const props = defineProps({
	item: {
		type: Object,
		required: true,
	},
})

const emit = defineEmits(["actioned"])
const busy = ref(false)

async function promptComment({ required }) {
	const alert = await alertController.create({
		header: required ? __("Reason for rejection") : __("Add a comment"),
		message: required
			? __("A comment is required when rejecting.")
			: __("Optional — visible on the document timeline."),
		inputs: [
			{
				name: "comment",
				type: "textarea",
				placeholder: __("Comment"),
			},
		],
		buttons: [
			{ text: __("Cancel"), role: "cancel" },
			{ text: __("Confirm"), role: "confirm" },
		],
	})
	await alert.present()
	const { role, data } = await alert.onDidDismiss()
	if (role !== "confirm") return undefined
	return (data?.values?.comment || "").trim()
}

function showToast(text, ok = true) {
	toast({
		title: ok ? __("Success") : __("Error"),
		text,
		icon: ok ? "check-circle" : "alert-circle",
		position: "bottom-center",
		iconClasses: ok ? "text-green-500" : "text-red-500",
	})
}

async function onApprove() {
	const comment = await promptComment({ required: false })
	if (comment === undefined) return // cancelled
	busy.value = true
	approveRequest.submit(
		{ doctype: props.item.doctype, name: props.item.name, comment: comment || null },
		{
			onSuccess() {
				busy.value = false
				showToast(__("Approved successfully!"))
				emit("actioned")
			},
			onError(err) {
				busy.value = false
				showToast(err?.messages?.[0] || __("Approval failed!"), false)
			},
		}
	)
}

async function onReject() {
	const comment = await promptComment({ required: true })
	if (comment === undefined) return // cancelled
	if (!comment) {
		showToast(__("A comment is required when rejecting."), false)
		return
	}
	busy.value = true
	rejectRequest.submit(
		{ doctype: props.item.doctype, name: props.item.name, comment },
		{
			onSuccess() {
				busy.value = false
				showToast(__("Rejected successfully!"))
				emit("actioned")
			},
			onError(err) {
				busy.value = false
				showToast(err?.messages?.[0] || __("Rejection failed!"), false)
			},
		}
	)
}
</script>
