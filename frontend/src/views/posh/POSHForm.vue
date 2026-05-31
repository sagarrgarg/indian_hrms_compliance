<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="w-full sm:w-96">
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
						{{ __("File a Complaint") }}
					</h2>
				</div>
			</div>
		</ion-header>

		<ion-content class="ion-no-padding">
			<div class="flex flex-col h-full w-screen sm:w-96">
				<div class="flex flex-col gap-5 p-4 pb-28">
					<!-- Confidentiality reassurance -->
					<div
						class="flex flex-row gap-3 rounded p-4 border-l-4"
						style="background: #fdecea; border-color: #d33"
					>
						<FeatherIcon
							name="shield"
							class="h-5 w-5 shrink-0 mt-0.5 text-red-700"
						/>
						<div class="text-xs text-red-700 leading-relaxed">
							{{
								__(
									"This complaint goes only to your company's Internal Committee. It is handled in strict confidence under the POSH Act, 2013."
								)
							}}
						</div>
					</div>

					<FormControl
						type="autocomplete"
						:label="__('Respondent (Accused)')"
						:options="employeeOptions"
						v-model="form.accused"
						:placeholder="__('Select the person the complaint is against')"
					/>

					<FormControl
						type="date"
						:label="__('Incident Date')"
						v-model="form.incident_date"
					/>

					<FormControl
						type="text"
						:label="__('Location')"
						v-model="form.incident_location"
						:placeholder="__('Where did it happen? (optional)')"
					/>

					<FormControl
						type="textarea"
						:label="__('Description of Incident')"
						v-model="form.incident_description"
						:placeholder="__('Describe the incident in your own words')"
					/>

					<div class="flex flex-col gap-2 bg-white rounded p-4">
						<div class="flex flex-row items-center justify-between">
							<label class="text-sm font-medium text-gray-800">
								{{ __("File anonymously") }}
							</label>
							<ion-toggle
								:checked="form.anonymous"
								@ionChange="form.anonymous = $event.detail.checked"
							/>
						</div>
						<div class="text-xs text-gray-500 leading-relaxed">
							{{
								__(
									"When enabled, your name is masked on lists and reports shown to the Internal Committee. Your identity is still recorded for the inquiry."
								)
							}}
						</div>
					</div>
				</div>

				<div class="flex flex-col gap-2 px-4">
					<Button
						variant="solid"
						class="w-full py-5 text-base"
						:loading="filePOSHComplaint.loading"
						:disabled="!isValid"
						@click="confirmSubmit"
					>
						{{ __("Submit Complaint") }}
					</Button>
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { inject, reactive, computed } from "vue"
import { useRouter } from "vue-router"
import {
	IonPage,
	IonHeader,
	IonContent,
	IonToggle,
	alertController,
} from "@ionic/vue"
import { Button, FormControl, FeatherIcon, toast } from "frappe-ui"

import { filePOSHComplaint, myPOSHComplaints } from "@/data/posh"
import { employees } from "@/data/employees"

const __ = inject("$translate")
const router = useRouter()

const employeeOptions = computed(() =>
	(employees.data || [])
		.filter((e) => e.isActive)
		.map((e) => ({
			label: e.employee_name
				? `${e.employee_name} (${e.name})`
				: e.name,
			value: e.name,
		}))
)

const form = reactive({
	accused: "",
	incident_date: null,
	incident_location: "",
	incident_description: "",
	anonymous: false,
})

const isValid = computed(
	() =>
		!!accusedValue.value &&
		!!form.incident_date &&
		!!form.incident_description
)

// FormControl autocomplete may return an object {label,value} or a string.
const accusedValue = computed(() =>
	form.accused && typeof form.accused === "object"
		? form.accused.value
		: form.accused
)

async function confirmSubmit() {
	const alert = await alertController.create({
		header: __("Submit POSH Complaint"),
		message: __(
			"This will file a confidential complaint with your company's Internal Committee. Please confirm the details are accurate."
		),
		buttons: [
			{ text: __("Cancel"), role: "cancel" },
			{ text: __("Submit"), handler: () => doSubmit() },
		],
	})
	await alert.present()
}

function doSubmit() {
	filePOSHComplaint.submit(
		{
			accused: accusedValue.value,
			incident_date: form.incident_date,
			incident_description: form.incident_description,
			incident_location: form.incident_location || null,
			anonymous: form.anonymous ? 1 : 0,
		},
		{
			onSuccess() {
				toast({
					title: __("Submitted"),
					text: __("Your complaint has been filed confidentially"),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
				myPOSHComplaints.reload()
				router.replace({ name: "POSHDashboard" })
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
