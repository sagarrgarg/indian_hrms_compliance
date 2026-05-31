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
						{{ __("File a Grievance") }}
					</h2>
				</div>
			</div>
		</ion-header>

		<ion-content class="ion-no-padding">
			<div class="flex flex-col h-full w-full sm:max-w-3xl sm:mx-auto">
				<div class="flex flex-col gap-5 p-4 pb-28">
					<FormControl
						type="text"
						:label="__('Subject')"
						v-model="form.subject"
						:placeholder="__('A short summary of your concern')"
					/>

					<FormControl
						type="select"
						:label="__('Grievance Type')"
						:options="typeOptions"
						v-model="form.grievance_type"
						@change="onTypeChange"
					/>

					<FormControl
						type="select"
						:label="__('Severity')"
						:options="severityOptions"
						v-model="form.severity"
					/>

					<FormControl
						type="textarea"
						:label="__('Description')"
						v-model="form.description"
						:placeholder="__('Describe what happened, when, and the impact on you')"
					/>
				</div>

				<div class="flex flex-col gap-2 px-4">
					<Button
						variant="solid"
						class="w-full py-5 text-base"
						:loading="fileGrievance.loading"
						:disabled="!isValid"
						@click="onSubmit"
					>
						{{ __("Submit Grievance") }}
					</Button>
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { inject, reactive, computed } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonHeader, IonContent } from "@ionic/vue"
import { Button, FormControl, FeatherIcon, toast } from "frappe-ui"

import {
	grievanceFormOptions,
	fileGrievance,
	myGrievances,
} from "@/data/grievances"

const __ = inject("$translate")
const router = useRouter()

grievanceFormOptions.fetch()

const options = computed(() => grievanceFormOptions.data || {})

const typeOptions = computed(() => [
	{ label: __("Select a type"), value: "" },
	...(options.value.grievance_types || []).map((t) => ({
		label: t.name,
		value: t.name,
	})),
])

const severityOptions = computed(() =>
	(options.value.severity_options || []).map((s) => ({
		label: s,
		value: s,
	}))
)

const form = reactive({
	subject: "",
	grievance_type: "",
	severity: "Medium",
	description: "",
})

function onTypeChange() {
	const t = (options.value.grievance_types || []).find(
		(x) => x.name === form.grievance_type
	)
	if (t?.default_severity) {
		form.severity = t.default_severity
	}
}

const isValid = computed(
	() => !!form.subject && !!form.grievance_type && !!form.description
)

function onSubmit() {
	fileGrievance.submit(
		{
			subject: form.subject,
			grievance_type: form.grievance_type,
			description: form.description,
			severity: form.severity,
		},
		{
			onSuccess() {
				toast({
					title: __("Success"),
					text: __("Grievance filed — it has been routed for review"),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
				myGrievances.reload()
				router.replace({ name: "GrievancesDashboard" })
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
