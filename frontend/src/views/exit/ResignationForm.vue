<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="w-full sm:max-w-3xl sm:mx-auto">
				<div
					class="flex flex-row bg-white shadow-sm py-4 px-3 items-center border-b"
				>
					<Button
						variant="ghost"
						class="!px-1 mr-1 hover:bg-white"
						@click="router.back()"
					>
						<FeatherIcon name="chevron-left" class="h-5 w-5" />
					</Button>
					<h2 class="text-xl font-semibold text-gray-900 truncate">
						{{ __("Initiate Resignation") }}
					</h2>
				</div>
			</div>
		</ion-header>

		<ion-content class="ion-no-padding">
			<div class="flex flex-col h-full w-full sm:max-w-3xl sm:mx-auto">
				<div class="flex flex-col gap-5 p-4 pb-28">
					<div class="flex flex-col gap-1 bg-white rounded p-4">
						<div class="text-base font-semibold text-gray-800">
							{{ defaults.employee_name || defaults.employee }}
						</div>
						<div class="text-xs text-gray-500">
							{{ defaults.company }}
						</div>
						<div
							v-if="defaults.notice_required_days != null"
							class="text-xs text-gray-500 mt-1"
						>
							{{ __("Contractual notice") }}:
							{{ defaults.notice_required_days }} {{ __("days") }}
						</div>
					</div>

					<FormControl
						type="select"
						:label="__('Reason Category')"
						:options="reasonOptions"
						v-model="form.reason_category"
					/>

					<FormControl
						type="textarea"
						:label="__('Reason Details')"
						v-model="form.reason_details"
						:placeholder="__('Optional — a short note for your manager / HR')"
					/>

					<FormControl
						type="number"
						:label="__('Notice Offered (days)')"
						v-model="form.notice_offered_days"
						@input="recomputeLastWorkingDate"
					/>

					<FormControl
						type="select"
						:label="__('Notice Disposition')"
						:options="dispositionOptions"
						v-model="form.notice_disposition"
					/>

					<FormControl
						type="date"
						:label="__('Intended Last Working Date')"
						v-model="form.intended_last_working_date"
					/>
				</div>

				<div class="flex flex-col gap-2 px-4">
					<Button
						variant="solid"
						class="w-full py-5 text-base"
						:loading="submitResignationRequest.loading"
						:disabled="!isValid"
						@click="confirmSubmit"
					>
						{{ __("Submit Resignation") }}
					</Button>
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { inject, reactive, computed, watch } from "vue"
import { useRouter } from "vue-router"
import {
	IonPage,
	IonHeader,
	IonContent,
	alertController,
} from "@ionic/vue"
import { Button, FormControl, FeatherIcon, toast } from "frappe-ui"

import {
	resignationFormDefaults,
	submitResignationRequest,
	myResignationStatus,
	myExitClearance,
	myExitDocuments,
} from "@/data/exit"

const __ = inject("$translate")
const dayjs = inject("$dayjs")
const router = useRouter()

resignationFormDefaults.fetch()

const defaults = computed(() => resignationFormDefaults.data || {})

const reasonOptions = computed(() => [
	{ label: __("Select a reason"), value: "" },
	...(defaults.value.reason_category_options || []).map((o) => ({
		label: o,
		value: o,
	})),
])

const dispositionOptions = computed(() =>
	(defaults.value.notice_disposition_options || []).map((o) => ({
		label: o,
		value: o,
	}))
)

const form = reactive({
	reason_category: "",
	reason_details: "",
	notice_offered_days: null,
	notice_disposition: "Will Serve in Full",
	intended_last_working_date: null,
})

// Seed notice_offered_days + last working day once defaults arrive.
watch(
	() => resignationFormDefaults.data,
	(d) => {
		if (!d) return
		if (form.notice_offered_days == null) {
			form.notice_offered_days = d.notice_required_days || 0
		}
		recomputeLastWorkingDate()
	},
	{ immediate: true }
)

function recomputeLastWorkingDate() {
	const days = parseInt(form.notice_offered_days, 10)
	if (isNaN(days)) return
	form.intended_last_working_date = dayjs()
		.add(days, "day")
		.format("YYYY-MM-DD")
}

const isValid = computed(() => !!form.reason_category)

async function confirmSubmit() {
	const alert = await alertController.create({
		header: __("Submit Resignation"),
		message: __(
			"This will notify your manager and HR. Are you sure you want to submit?"
		),
		buttons: [
			{ text: __("Cancel"), role: "cancel" },
			{ text: __("Submit"), handler: () => doSubmit() },
		],
	})
	await alert.present()
}

function doSubmit() {
	submitResignationRequest.submit(
		{
			reason_category: form.reason_category,
			reason_details: form.reason_details,
			notice_offered_days: form.notice_offered_days,
			notice_disposition: form.notice_disposition,
			intended_last_working_date: form.intended_last_working_date,
		},
		{
			onSuccess() {
				toast({
					title: __("Success"),
					text: __("Resignation submitted — your manager and HR were notified"),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
				myResignationStatus.reload()
				myExitClearance.reload()
				myExitDocuments.reload()
				router.replace({ name: "ExitDashboard" })
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
