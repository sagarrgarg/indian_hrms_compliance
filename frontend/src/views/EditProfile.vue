<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="w-full sm:max-w-3xl sm:mx-auto">
				<div class="flex flex-row bg-white shadow-sm py-4 px-3 items-center border-b">
					<Button variant="ghost" class="!px-1 mr-1 hover:bg-white" @click="router.back()">
						<FeatherIcon name="chevron-left" class="h-5 w-5" />
					</Button>
					<h2 class="text-xl font-semibold text-gray-900 truncate">
						{{ __("Request Profile Update") }}
					</h2>
				</div>
			</div>
		</ion-header>

		<ion-content>
			<div class="w-full sm:max-w-3xl sm:mx-auto p-4 flex flex-col gap-4 pb-32">
				<!-- Intro -->
				<div class="bg-indigo-50 border border-indigo-100 rounded-xl p-4 text-sm text-indigo-900">
					<div class="font-semibold mb-1">{{ __("How this works") }}</div>
					<ul class="list-disc pl-5 space-y-1">
						<li>{{ __("Edit only the fields that changed. Leave the rest blank.") }}</li>
						<li>{{ __("HR will review and approve before your record is updated.") }}</li>
						<li>{{ __("Sensitive fields (PAN, Aadhaar, bank a/c) show only the last few characters of your current value.") }}</li>
					</ul>
				</div>

				<EmptyState
					v-if="editableProfileFields.loading && !editableProfileFields.data"
					:message="__('Loading...')"
				/>

				<!-- Load error (e.g. User not linked to an active Employee) -->
				<div
					v-else-if="editableProfileFields.error"
					class="bg-red-50 border border-red-100 rounded-xl p-4 text-sm text-red-800"
				>
					<div class="font-semibold mb-1">{{ __("Couldn't load your profile fields") }}</div>
					<div>{{ errorMessage }}</div>
				</div>

				<!-- Loaded, but nothing editable is configured -->
				<EmptyState
					v-else-if="!(editableProfileFields.data || []).length"
					:message="__('No editable fields are available. Please contact HR.')"
				/>

				<!-- Fields -->
				<div
					v-for="f in editableProfileFields.data || []"
					:key="f.fieldname"
					class="bg-white rounded-xl border border-gray-100 p-4 flex flex-col gap-2"
				>
					<div class="flex items-center justify-between">
						<label class="text-sm font-medium text-gray-800">{{ f.label }}</label>
						<span
							v-if="f.sensitive"
							class="text-[10px] uppercase tracking-wide text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full"
						>
							{{ __("Sensitive") }}
						</span>
					</div>

					<div v-if="f.current" class="text-xs text-gray-500">
						{{ __("On file:") }} <span class="font-mono">{{ f.current }}</span>
					</div>
					<div v-else class="text-xs text-gray-400 italic">
						{{ __("On file: not set") }}
					</div>

					<input
						v-if="!isSelect(f) && !isTextarea(f)"
						:type="inputType(f)"
						v-model="proposed[f.fieldname]"
						:placeholder="f.sensitive ? __('Leave blank to keep') : __('New value (leave blank to keep)')"
						class="w-full border border-gray-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200"
					/>
					<select
						v-else-if="isSelect(f)"
						v-model="proposed[f.fieldname]"
						class="w-full border border-gray-200 rounded-md px-3 py-2 text-sm bg-white"
					>
						<option value="">{{ __("— no change —") }}</option>
						<option v-for="opt in selectOptions(f)" :key="opt" :value="opt">{{ opt }}</option>
					</select>
					<textarea
						v-else
						v-model="proposed[f.fieldname]"
						rows="2"
						:placeholder="__('New value (leave blank to keep)')"
						class="w-full border border-gray-200 rounded-md px-3 py-2 text-sm"
					/>

					<div v-if="f.description" class="text-xs text-gray-400 mt-1">{{ f.description }}</div>
				</div>

				<!-- Consent -->
				<div class="bg-white rounded-xl border border-gray-100 p-4 flex items-start gap-3">
					<input type="checkbox" v-model="consent" class="mt-1" />
					<div class="text-sm text-gray-700">
						{{ __("I confirm the information above is accurate and consent to its processing under the DPDP Act, 2023.") }}
					</div>
				</div>

				<!-- Submit -->
				<div class="flex flex-col gap-2">
					<div v-if="changedCount === 0" class="text-xs text-gray-500 text-center">
						{{ __("No changes detected — fill in at least one field to submit.") }}
					</div>
					<Button
						variant="solid"
						class="w-full py-5 text-base"
						:loading="submitProfileChange.loading"
						:disabled="changedCount === 0 || !consent"
						@click="onSubmit"
					>
						{{ __("Submit {0} change(s) for HR approval", [changedCount]) }}
					</Button>
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { computed, inject, reactive, ref, onMounted, onBeforeUnmount } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonHeader, IonContent } from "@ionic/vue"
import { Button, FeatherIcon, toast } from "frappe-ui"

import EmptyState from "@/components/EmptyState.vue"
import { editableProfileFields, submitProfileChange } from "@/data/profileChange"

const __ = inject("$translate")
const router = useRouter()
const socket = inject("$socket")

// Reactive map of fieldname → new value the user has typed.
const proposed = reactive({})
const consent = ref(false)

function onEmployeeUpdate(d) {
	// HR may have just approved a request; reload to refresh "On file" values.
	if (d?.doctype === "Employee") editableProfileFields.reload()
}

const errorMessage = computed(() => {
	const e = editableProfileFields.error
	if (!e) return ""
	return (
		(e.messages && e.messages.join(", ")) ||
		e.message ||
		__("Something went wrong while loading your profile. Please try again.")
	)
})

onMounted(() => {
	editableProfileFields
		.fetch()
		.then(() => {
			for (const f of editableProfileFields.data || []) {
				if (!(f.fieldname in proposed)) proposed[f.fieldname] = ""
			}
		})
		.catch(() => {
			// error is surfaced via editableProfileFields.error in the template
		})
	socket.emit("doctype_subscribe", "Employee")
	socket.on("list_update", onEmployeeUpdate)
})

onBeforeUnmount(() => {
	socket.emit("doctype_unsubscribe", "Employee")
	socket.off("list_update", onEmployeeUpdate)
})

const changedCount = computed(() =>
	Object.values(proposed).filter((v) => v !== null && String(v).trim() !== "").length
)

function isSelect(f) {
	return f.fieldtype === "Select" && f.options
}
function isTextarea(f) {
	return ["Small Text", "Text", "Long Text"].includes(f.fieldtype)
}
function inputType(f) {
	if (f.fieldtype === "Date") return "date"
	if (f.fieldtype === "Datetime") return "datetime-local"
	if (f.fieldtype === "Int" || f.fieldtype === "Float" || f.fieldtype === "Currency") return "number"
	return "text"
}
function selectOptions(f) {
	return String(f.options || "")
		.split("\n")
		.map((s) => s.trim())
		.filter(Boolean)
}

function onSubmit() {
	const changes = Object.entries(proposed)
		.filter(([, v]) => v !== null && String(v).trim() !== "")
		.map(([fieldname, new_value]) => ({ fieldname, new_value: String(new_value).trim() }))
	if (!changes.length) return
	submitProfileChange.submit(
		{ changes, dpdp_consent: 1 },
		{
			onSuccess(result) {
				toast({
					title: __("Submitted"),
					text: __("Sent {0} change(s) to HR for approval.", [result?.count ?? changes.length]),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
				// Route to history so the employee can see Pending status + HR notes.
				router.replace({ name: "MyProfileUpdates" })
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
