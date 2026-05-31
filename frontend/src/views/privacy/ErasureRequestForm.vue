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
						{{ __("Request Data Erasure") }}
					</h2>
				</div>
			</div>
		</ion-header>

		<ion-content class="ion-no-padding">
			<div class="flex flex-col h-full w-full sm:max-w-3xl sm:mx-auto">
				<div class="flex flex-col gap-5 p-4 pb-28">
					<div
						class="flex flex-row items-start gap-2 bg-amber-50 rounded p-4 border border-amber-200"
					>
						<FeatherIcon
							name="alert-triangle"
							class="h-4 w-4 text-amber-600 mt-0.5 shrink-0"
						/>
						<div class="text-sm text-amber-800 leading-relaxed">
							{{
								__(
									"Your request goes through mandatory legal review. Some data has statutory retention obligations (e.g. provident fund, tax records) and may have to be retained even if you request erasure."
								)
							}}
						</div>
					</div>

					<FormControl
						type="select"
						:label="__('Scope')"
						:options="scopeOptions"
						v-model="form.scope"
					/>

					<FormControl
						v-if="form.scope === 'Specific Data Categories'"
						type="textarea"
						:label="__('Specific Data Categories')"
						v-model="form.specific_categories"
						:placeholder="
							__('e.g. bank account details, emergency contact')
						"
					/>

					<FormControl
						type="textarea"
						:label="__('Reason (optional)')"
						v-model="form.reason"
						:placeholder="__('Why are you requesting erasure?')"
					/>
				</div>

				<div class="flex flex-col gap-2 px-4">
					<Button
						variant="solid"
						theme="red"
						class="w-full py-5 text-base"
						:loading="requestDataErasure.loading"
						:disabled="!isValid"
						@click="onSubmit"
					>
						{{ __("Submit Erasure Request") }}
					</Button>
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { inject, reactive, computed } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonHeader, IonContent, alertController } from "@ionic/vue"
import { Button, FormControl, FeatherIcon, toast } from "frappe-ui"

import { requestDataErasure, myErasureRequests } from "@/data/privacy"

const __ = inject("$translate")
const router = useRouter()

const scopeOptions = [
	{ label: __("Full Profile"), value: "Full Profile" },
	{
		label: __("Specific Data Categories"),
		value: "Specific Data Categories",
	},
]

const form = reactive({
	scope: "Specific Data Categories",
	specific_categories: "",
	reason: "",
})

const isValid = computed(
	() =>
		!!form.scope &&
		(form.scope !== "Specific Data Categories" ||
			!!form.specific_categories.trim())
)

async function onSubmit() {
	const alert = await alertController.create({
		header: __("Confirm Erasure Request"),
		message: __(
			"This request will be reviewed by the legal team. Data subject to statutory retention may be kept. Do you want to proceed?"
		),
		buttons: [
			{ text: __("Cancel"), role: "cancel" },
			{ text: __("Submit"), role: "confirm", handler: submit },
		],
	})
	await alert.present()
}

function submit() {
	requestDataErasure.submit(
		{
			scope: form.scope,
			specific_categories:
				form.scope === "Specific Data Categories"
					? form.specific_categories
					: null,
			reason: form.reason || null,
		},
		{
			onSuccess() {
				toast({
					title: __("Success"),
					text: __("Erasure request filed — it is now under review"),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
				myErasureRequests.reload()
				router.replace({ name: "PrivacyDashboard" })
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
