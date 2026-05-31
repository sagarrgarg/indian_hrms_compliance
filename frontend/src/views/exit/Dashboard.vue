<template>
	<BaseLayout :pageTitle="__('Resignation & Exit')">
		<template #body>
			<div class="flex flex-col mt-7 mb-7 px-4 py-4 gap-5 pb-24">
				<!-- No active resignation: explain process + initiate -->
				<div
					v-if="!hasActiveResignation"
					class="flex flex-col gap-4 bg-white rounded p-5"
				>
					<div class="text-lg font-bold text-gray-900">
						{{ __("Planning to move on?") }}
					</div>
					<div class="text-sm text-gray-600 leading-relaxed">
						{{
							__(
								"Initiating your resignation notifies your reporting manager and HR. You'll pick your notice period, see your computed last working day, and then track no-dues clearance and exit documents right here."
							)
						}}
					</div>
					<Button
						variant="solid"
						class="w-full py-5 text-base"
						@click="goToResign"
					>
						{{ __("Initiate Resignation") }}
					</Button>
				</div>

				<!-- Active resignation: status card -->
				<div
					v-else
					class="flex flex-col gap-3 bg-white rounded p-5"
				>
					<div class="flex flex-row items-center justify-between">
						<div class="text-lg font-bold text-gray-900">
							{{ resignation.request_type }}
						</div>
						<ion-badge :color="stateColor">
							{{ resignation.workflow_state }}
						</ion-badge>
					</div>

					<div class="flex flex-col gap-2 mt-1">
						<div
							v-if="resignation.submission_date"
							class="flex flex-row justify-between"
						>
							<span class="text-sm text-gray-500">{{ __("Submitted") }}</span>
							<span class="text-sm font-medium text-gray-800">
								{{ dayjs(resignation.submission_date).format("D MMM YYYY") }}
							</span>
						</div>
						<div
							v-if="resignation.intended_last_working_date"
							class="flex flex-row justify-between"
						>
							<span class="text-sm text-gray-500">
								{{ __("Last Working Day") }}
							</span>
							<span class="text-sm font-medium text-gray-800">
								{{
									dayjs(resignation.intended_last_working_date).format(
										"D MMM YYYY"
									)
								}}
							</span>
						</div>
						<div
							v-if="resignation.notice_disposition"
							class="flex flex-row justify-between"
						>
							<span class="text-sm text-gray-500">
								{{ __("Notice Disposition") }}
							</span>
							<span class="text-sm font-medium text-gray-800">
								{{ resignation.notice_disposition }}
							</span>
						</div>
						<div
							v-if="resignation.reason_category"
							class="flex flex-row justify-between"
						>
							<span class="text-sm text-gray-500">{{ __("Reason") }}</span>
							<span class="text-sm font-medium text-gray-800">
								{{ resignation.reason_category }}
							</span>
						</div>
					</div>

					<Button
						v-if="resignation.can_withdraw"
						variant="outline"
						class="w-full mt-2"
						:loading="withdrawResignationRequest.loading"
						@click="confirmWithdraw"
					>
						{{ __("Withdraw Resignation") }}
					</Button>
				</div>

				<!-- No-dues clearance tracker -->
				<div
					v-if="hasActiveResignation && clearanceItems.length"
					class="flex flex-col gap-3"
				>
					<div class="text-base font-semibold text-gray-700">
						{{ __("No-Dues Clearance") }}
						<span
							v-if="boardingStatus"
							class="text-xs text-gray-400 font-normal ml-1"
						>
							({{ boardingStatus }})
						</span>
					</div>
					<ClearanceItem
						v-for="(item, idx) in clearanceItems"
						:key="idx"
						:item="item"
					/>
				</div>

				<!-- Exit documents -->
				<div v-if="hasDocuments" class="flex flex-col gap-3">
					<div class="text-base font-semibold text-gray-700">
						{{ __("Exit Documents") }}
					</div>
					<DocumentItem
						v-for="letter in documents.letters"
						:key="letter.name"
						:title="letter.letter_type"
						:subtitle="
							letter.date
								? dayjs(letter.date).format('D MMM YYYY')
								: letter.company
						"
						:href="letter.print_url"
					/>
					<DocumentItem
						v-for="f16 in documents.form16"
						:key="f16.name"
						:title="__('Form 16') + ' — ' + f16.fiscal_year"
						:subtitle="
							f16.issued_on
								? __('Issued') + ' ' + dayjs(f16.issued_on).format('D MMM YYYY')
								: f16.company
						"
						:href="f16.signed_pdf"
					/>
				</div>

				<EmptyState
					v-if="
						hasActiveResignation &&
						!clearanceItems.length &&
						!hasDocuments
					"
					:message="
						__('Clearance items and exit documents appear here as HR processes your exit.')
					"
				/>
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { inject, computed } from "vue"
import { useRouter } from "vue-router"
import { IonBadge, alertController } from "@ionic/vue"
import { Button, toast } from "frappe-ui"

import BaseLayout from "@/components/BaseLayout.vue"
import EmptyState from "@/components/EmptyState.vue"
import ClearanceItem from "@/components/ClearanceItem.vue"
import DocumentItem from "@/components/DocumentItem.vue"

import {
	myResignationStatus,
	myExitClearance,
	myExitDocuments,
	withdrawResignationRequest,
} from "@/data/exit"

const __ = inject("$translate")
const dayjs = inject("$dayjs")
const router = useRouter()

const resignation = computed(() => myResignationStatus.data || {})
const hasActiveResignation = computed(() => !!resignation.value?.name)

const clearanceItems = computed(
	() => myExitClearance.data?.no_dues_items || []
)
const boardingStatus = computed(() => myExitClearance.data?.boarding_status)

const documents = computed(
	() => myExitDocuments.data || { letters: [], form16: [] }
)
const hasDocuments = computed(
	() =>
		(documents.value.letters?.length || 0) +
			(documents.value.form16?.length || 0) >
		0
)

const stateColor = computed(() => {
	switch (resignation.value?.workflow_state) {
		case "Approved":
			return "success"
		case "Rejected":
		case "Withdrawn":
			return "danger"
		default:
			return "warning"
	}
})

function goToResign() {
	router.push({ name: "ResignationForm" })
}

async function confirmWithdraw() {
	const alert = await alertController.create({
		header: __("Withdraw Resignation"),
		message: __(
			"This will withdraw your resignation request. Your manager and HR will be notified."
		),
		buttons: [
			{ text: __("Cancel"), role: "cancel" },
			{
				text: __("Withdraw"),
				role: "destructive",
				handler: () => doWithdraw(),
			},
		],
	})
	await alert.present()
}

function doWithdraw() {
	withdrawResignationRequest.submit(
		{ name: resignation.value.name },
		{
			onSuccess() {
				toast({
					title: __("Success"),
					text: __("Resignation withdrawn"),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
				myResignationStatus.reload()
				myExitClearance.reload()
				myExitDocuments.reload()
			},
			onError(error) {
				toast({
					title: __("Error"),
					text: __(error?.messages?.[0] || error.message),
					icon: "alert-circle",
					position: "bottom-center",
					iconClasses: "text-red-500",
				})
			},
		}
	)
}
</script>
