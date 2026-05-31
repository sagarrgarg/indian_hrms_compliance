<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="w-full sm:max-w-3xl sm:mx-auto">
				<div
					class="flex flex-row bg-white shadow-sm py-4 px-3 items-center border-b"
				>
					<Button variant="ghost" class="!px-1 mr-1 hover:bg-white" @click="router.back()">
						<FeatherIcon name="chevron-left" class="h-5 w-5" />
					</Button>
					<h2 class="text-xl font-semibold text-gray-900 truncate">
						{{ __("Task") }}
					</h2>
				</div>
			</div>
		</ion-header>

		<ion-content class="ion-no-padding">
			<div class="flex flex-col h-full w-full sm:max-w-3xl sm:mx-auto">
				<div v-if="task" class="flex flex-col gap-5 p-4 pb-28">
					<div class="flex flex-col gap-2">
						<div class="text-xl font-bold text-gray-900">
							{{ task.goal_name }}
						</div>
						<div class="flex flex-row items-center gap-2 flex-wrap">
							<ion-badge v-if="task.kra" color="medium">{{ task.kra }}</ion-badge>
							<ion-badge :color="task.status === 'Completed' ? 'success' : 'warning'">
								{{ task.status }}
							</ion-badge>
						</div>
					</div>

					<div class="flex flex-col gap-3 bg-white rounded p-4">
						<div v-if="task.period_label" class="flex flex-row justify-between">
							<span class="text-sm text-gray-500">{{ __("Period") }}</span>
							<span class="text-sm font-medium text-gray-800">
								{{ task.period_label }}
							</span>
						</div>
						<div v-if="task.due_date" class="flex flex-row justify-between">
							<span class="text-sm text-gray-500">{{ __("Due Date") }}</span>
							<span class="text-sm font-medium text-gray-800">
								{{ dayjs(task.due_date).format("D MMM YYYY") }}
							</span>
						</div>
						<div class="flex flex-row justify-between">
							<span class="text-sm text-gray-500">{{ __("Completion") }}</span>
							<span class="text-sm font-medium text-gray-800">
								{{ task.completion_type || __("Checkbox") }}
							</span>
						</div>
					</div>

					<div v-if="!isClosed" class="flex flex-col gap-4">
						<FormControl
							v-if="task.completion_type === 'Numeric Entry'"
							type="number"
							:label="__('Value')"
							v-model="numericValue"
							:placeholder="__('Enter measured value')"
						/>

						<div
							v-if="task.completion_type === 'Document Upload'"
							class="flex flex-col gap-2"
						>
							<label class="text-sm text-gray-600">{{ __("Attachment") }}</label>
							<input
								type="file"
								class="text-sm"
								@change="onFileSelect"
							/>
							<span v-if="uploadedFileUrl" class="text-xs text-green-600">
								{{ __("File ready") }}
							</span>
						</div>

						<div v-if="task.delegated_from" class="flex flex-col gap-2">
							<div class="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded p-2">
								{{ __("Leave cover — delegated from {0}. Record who actually performed it.", [task.delegated_from]) }}
							</div>
							<FormControl
								type="autocomplete"
								:label="__('Performed by')"
								:options="employeeOptions"
								v-model="performedBy"
								:placeholder="__('Select employee')"
							/>
						</div>

						<FormControl
							type="textarea"
							:label="__('Notes')"
							v-model="notes"
							:placeholder="__('Optional notes')"
						/>
					</div>

					<div v-else class="flex flex-col gap-3 bg-gray-50 rounded p-4 border">
						<div
							v-if="task.numeric_value"
							class="flex flex-row justify-between"
						>
							<span class="text-sm text-gray-500">{{ __("Value") }}</span>
							<span class="text-sm font-medium text-gray-800">
								{{ task.numeric_value }}
							</span>
						</div>
						<div v-if="task.task_notes" class="text-sm text-gray-700">
							{{ task.task_notes }}
						</div>
						<a
							v-if="task.task_attachment"
							:href="task.task_attachment"
							target="_blank"
							rel="noopener"
							class="flex flex-row items-center gap-2 text-blue-600 text-sm font-medium"
						>
							<FeatherIcon name="paperclip" class="h-4 w-4" />
							{{ __("View attachment") }}
						</a>
					</div>
				</div>

				<EmptyState v-else :message="__('Task not found')" />
			</div>
		</ion-content>

		<ion-footer v-if="task && !isClosed" class="ion-no-border">
			<div class="w-full sm:max-w-3xl sm:mx-auto bg-white p-4 border-t">
				<Button
					variant="solid"
					class="w-full py-5 text-base"
					:loading="completeTask.loading || isUploading"
					:disabled="isSubmitDisabled"
					@click="onComplete"
				>
					{{ requiresApproval ? __("Submit for Approval") : __("Mark Complete") }}
				</Button>
			</div>
		</ion-footer>
	</ion-page>
</template>

<script setup>
import { inject, computed, ref } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonHeader, IonContent, IonFooter, IonBadge } from "@ionic/vue"
import { Button, FormControl, FeatherIcon, toast } from "frappe-ui"

import EmptyState from "@/components/EmptyState.vue"
import { FileAttachment } from "@/composables"

import { myTasks as tasks, myTaskSummary, completeTask } from "@/data/tasks"
import { employees } from "@/data/employees"

const props = defineProps({
	id: {
		type: String,
		required: true,
	},
})

const __ = inject("$translate")
const dayjs = inject("$dayjs")
const router = useRouter()

const numericValue = ref(null)
const notes = ref("")
const uploadedFileUrl = ref("")
const isUploading = ref(false)
const performedBy = ref(null)

const employeeOptions = computed(() =>
	(employees.data || [])
		.filter((e) => e.status === "Active")
		.map((e) => ({ label: `${e.employee_name} (${e.name})`, value: e.name })),
)

const task = computed(() => tasks.data?.find((t) => t.name === props.id))
const requiresApproval = computed(() => !!task.value?.requires_approval)
const isClosed = computed(() =>
	["Completed", "Archived", "Closed"].includes(task.value?.status)
)

const isSubmitDisabled = computed(() => {
	if (task.value?.delegated_from && !performedBy.value?.value) {
		return true
	}
	if (task.value?.completion_type === "Numeric Entry") {
		return numericValue.value === null || numericValue.value === ""
	}
	if (task.value?.completion_type === "Document Upload") {
		return !uploadedFileUrl.value
	}
	return false
})

async function onFileSelect(e) {
	const file = e.target.files?.[0]
	if (!file) return
	isUploading.value = true
	try {
		const fileAttachment = new FileAttachment(file)
		const fileDoc = await fileAttachment.upload("Goal", props.id, "task_attachment")
		uploadedFileUrl.value = fileDoc?.file_url || ""
	} catch (error) {
		toast({
			title: __("Error"),
			text: __("File upload failed"),
			icon: "alert-circle",
			position: "bottom-center",
			iconClasses: "text-red-500",
		})
	} finally {
		isUploading.value = false
	}
}

function onComplete() {
	const params = { goal_name: props.id }
	if (task.value?.completion_type === "Numeric Entry") {
		params.numeric_value = numericValue.value
	}
	if (notes.value) params.notes = notes.value
	if (uploadedFileUrl.value) params.attachment = uploadedFileUrl.value
	if (task.value?.delegated_from) params.performed_by = performedBy.value?.value

	completeTask.submit(params, {
		onSuccess() {
			toast({
				title: __("Success"),
				text: requiresApproval.value
					? __("Submitted for approval")
					: __("Task completed"),
				icon: "check-circle",
				position: "bottom-center",
				iconClasses: "text-green-500",
			})
			tasks.reload()
			myTaskSummary.reload()
			router.back()
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
	})
}
</script>
