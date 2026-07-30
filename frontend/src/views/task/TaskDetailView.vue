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
							<ion-badge :color="statusBadge.color">{{ statusBadge.label }}</ion-badge>
							<ion-badge v-if="task.risk_tier === 'Critical'" color="danger">
								{{ __("Critical") }}
							</ion-badge>
						</div>
					</div>

					<!-- Sent back by the approver: show WHY, prominently, so the
					     employee knows what to fix before resubmitting. -->
					<div
						v-if="task.was_sent_back && task.approval_notes"
						class="flex flex-col gap-1 rounded border border-amber-200 bg-amber-50 p-3"
					>
						<div class="flex flex-row items-center gap-2 text-sm font-semibold text-amber-800">
							<FeatherIcon name="corner-up-left" class="h-4 w-4" />
							{{ __("Sent back for changes") }}
						</div>
						<div class="text-sm text-amber-900">{{ task.approval_notes }}</div>
					</div>

					<!-- Submitted and waiting on someone else — read-only. -->
					<div
						v-else-if="task.awaiting_approval"
						class="flex flex-row items-center gap-2 rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900"
					>
						<FeatherIcon name="clock" class="h-4 w-4 shrink-0" />
						<span>{{ __("Submitted — awaiting approval.") }}</span>
					</div>

					<!-- Approved: who signed off, and when. The audit trail, shown. -->
					<div
						v-else-if="task.approved_by"
						class="flex flex-col gap-1 rounded border border-green-200 bg-green-50 p-3"
					>
						<div class="flex flex-row items-center gap-2 text-sm font-semibold text-green-800">
							<FeatherIcon name="check-circle" class="h-4 w-4" />
							{{ __("Approved by {0}", [task.approved_by_name || task.approved_by]) }}
						</div>
						<div v-if="task.approved_at" class="text-xs text-green-700">
							{{ dayjs(task.approved_at).format("D MMM YYYY, h:mm a") }}
						</div>
						<div v-if="task.approval_notes" class="text-sm text-green-900">
							{{ task.approval_notes }}
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

					<!-- Playbook: the documented 'how', as a tick-through checklist. A
					     reference to follow — ticks are not the task's evidence. -->
					<div v-if="playbook" class="flex flex-col gap-2 bg-white rounded p-4">
						<div class="flex flex-row items-center justify-between">
							<span class="text-sm font-semibold text-gray-800">
								{{ __("Playbook") }}: {{ playbook.title }}
							</span>
							<span v-if="playbook.version" class="text-xs text-gray-400">
								{{ __("v{0}", [playbook.version]) }}
							</span>
						</div>
						<ul class="flex flex-col gap-1.5">
							<li
								v-for="(s, i) in playbook.steps"
								:key="i"
								class="flex flex-row items-start gap-2 text-sm"
							>
								<input
									type="checkbox"
									class="mt-1 shrink-0"
									:checked="!!checked[i]"
									@change="checked[i] = !checked[i]"
								/>
								<div class="flex flex-col">
									<span :class="checked[i] ? 'text-gray-400 line-through' : 'text-gray-800'">
										{{ s.step_text }}
										<span
											v-if="s.is_control_point"
											class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] bg-red-50 text-red-600"
										>{{ __("Control") }}</span>
									</span>
									<span v-if="s.expected_evidence" class="text-xs text-gray-400">
										{{ __("Evidence") }}: {{ s.expected_evidence }}
									</span>
								</div>
							</li>
						</ul>
					</div>

					<!-- This instance is already split across the team. -->
					<div
						v-if="task.has_distributed_children"
						class="flex flex-row items-center gap-2 rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900"
					>
						<FeatherIcon name="users" class="h-4 w-4 shrink-0" />
						<span>{{ __("Distributed to your reports — completes when they all finish.") }}</span>
					</div>

					<!-- Head: distribute this Accountable instance to reports. -->
					<div
						v-else-if="canDistribute && !isLocked"
						class="flex flex-col gap-2 bg-white rounded p-4"
					>
						<span class="text-sm font-semibold text-gray-800">{{ __("Distribute to your team") }}</span>
						<span class="text-xs text-gray-500">
							{{ __("Split this into sub-tasks for your reports, or just do it yourself below.") }}
						</span>
						<label
							v-for="m in myReports"
							:key="m.name"
							class="flex flex-row items-center gap-2 text-sm text-gray-800"
						>
							<input type="checkbox" :value="m.name" v-model="selectedReports" />
							{{ m.employee_name }}
						</label>
						<span v-if="!myReports.length" class="text-xs text-gray-400">
							{{ __("You have no direct reports to distribute to.") }}
						</span>
						<Button
							v-if="myReports.length"
							variant="subtle"
							:loading="distributing"
							:disabled="!selectedReports.length"
							@click="onDistribute"
						>
							{{ __("Distribute to {0} report(s)", [selectedReports.length]) }}
						</Button>
					</div>

					<!-- Report: bounce a distributed sub-task back to the head. -->
					<div v-if="task.is_distributed_child && !isLocked" class="flex justify-end">
						<Button variant="ghost" class="text-amber-700" @click="onBounce">
							<template #prefix><FeatherIcon name="corner-up-left" class="h-4 w-4" /></template>
							{{ __("Bounce back to manager") }}
						</Button>
					</div>

					<div v-if="!isLocked" class="flex flex-col gap-4">
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

		<ion-footer v-if="task && !isLocked" class="ion-no-border">
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

		<!-- Re-opening an APPROVED task would erase the approver's sign-off, so the
		     API refuses it for the doer. Don't offer a button that always fails. -->
		<ion-footer
			v-else-if="task && task.status === 'Completed' && !task.approved_by"
			class="ion-no-border"
		>
			<div class="w-full sm:max-w-3xl sm:mx-auto bg-white p-4 border-t">
				<Button
					variant="subtle"
					class="w-full py-5 text-base"
					:loading="reopenTask.loading"
					@click="onReopen"
				>
					{{ __("Mark as not completed") }}
				</Button>
			</div>
		</ion-footer>

		<!-- Submitted but not yet decided: let the employee pull it back to fix a
		     mistake instead of waiting for the approver to reject it. -->
		<ion-footer
			v-else-if="task && task.awaiting_approval && !task.approved_by"
			class="ion-no-border"
		>
			<div class="w-full sm:max-w-3xl sm:mx-auto bg-white p-4 border-t">
				<Button
					variant="subtle"
					class="w-full py-5 text-base"
					:loading="reopenTask.loading"
					@click="onReopen"
				>
					{{ __("Withdraw submission") }}
				</Button>
			</div>
		</ion-footer>
	</ion-page>
</template>

<script setup>
import { inject, computed, ref, watch, reactive } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonHeader, IonContent, IonFooter, IonBadge } from "@ionic/vue"
import { Button, FormControl, FeatherIcon, toast, createResource } from "frappe-ui"

import EmptyState from "@/components/EmptyState.vue"
import { FileAttachment } from "@/composables"

import {
	myTasks as tasks,
	myTaskSummary,
	completeTask,
	reopenTask,
	myTeam,
	distributeTask,
	bounceTask,
} from "@/data/tasks"
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

// --- Head distribution (Assign-to-Head) ---
const distributing = ref(false)
const selectedReports = ref([])
const myReports = computed(() => (myTeam.data || []).filter((m) => !m.is_self))
const canDistribute = computed(
	() => !!task.value?.can_distribute && !task.value?.has_distributed_children,
)
async function onDistribute() {
	if (!selectedReports.value.length) return
	distributing.value = true
	try {
		await distributeTask.submit({ goal_name: task.value.name, employees: selectedReports.value })
		tasks.reload()
		selectedReports.value = []
		toast.success(__("Distributed to your reports"))
	} catch (e) {
		toast.error(e?.messages?.[0] || __("Could not distribute"))
	} finally {
		distributing.value = false
	}
}
async function onBounce() {
	const reason = window.prompt(__("Why are you bouncing this back to your manager?"))
	if (!reason || !reason.trim()) return
	try {
		await bounceTask.submit({ goal_name: task.value.name, comment: reason })
		tasks.reload()
		router.back()
		toast.success(__("Bounced back to your manager"))
	} catch (e) {
		toast.error(e?.messages?.[0] || __("Could not bounce"))
	}
}

// Playbook tick-through checklist — a reference the doer follows; local tick
// state only (the task's own completion_type still captures the real evidence).
const playbook = ref(null)
const checked = reactive({})
const playbookResource = createResource({
	url: "indian_hrms_compliance.hr.doctype.playbook.playbook.get_playbook_steps",
	onSuccess(data) {
		// Discard a stale response: if the user has already navigated to a task
		// with a different playbook, this reply is for the wrong one.
		if (data && data.name && data.name !== task.value?.playbook) return
		playbook.value = data && data.steps && data.steps.length ? data : null
	},
})
// Reset the local tick state whenever the task changes — keyed on the task ID,
// not the playbook name, so navigating between two tasks that share one playbook
// still clears A's ticks off B.
watch(() => props.id, () => {
	for (const k in checked) delete checked[k]
})
// Fetch (or clear) the checklist when the resolved playbook changes. Keyed on
// the value so it also fires when `tasks.data` loads async after mount and the
// task — and its playbook — first become available.
watch(
	() => task.value?.playbook,
	(pb) => {
		playbook.value = null
		if (pb) playbookResource.fetch({ playbook: pb })
	},
	{ immediate: true },
)
const isClosed = computed(() =>
	["Completed", "Archived", "Closed"].includes(task.value?.status)
)
// Submitted and waiting on an approver: the employee must not be able to
// re-submit or edit their evidence while it's under review.
const isAwaiting = computed(() => !!task.value?.awaiting_approval)
// A distributed parent auto-completes from its children; the head can't tick it
// directly, so lock its completion controls too.
const isLocked = computed(
	() => isClosed.value || isAwaiting.value || !!task.value?.has_distributed_children,
)

const statusBadge = computed(() => {
	const t = task.value
	if (!t) return { label: "", color: "medium" }
	if (t.status === "Completed") return { label: __("Completed"), color: "success" }
	if (isAwaiting.value) return { label: __("Awaiting approval"), color: "primary" }
	if (t.was_sent_back) return { label: __("Sent back"), color: "warning" }
	if (["Archived", "Closed"].includes(t.status))
		return { label: __(t.status), color: "medium" }
	return { label: __(t.status), color: "warning" }
})

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

function onReopen() {
	reopenTask.submit(
		{ goal_name: props.id },
		{
			onSuccess() {
				toast({
					title: __("Reopened"),
					text: __("Task marked as not completed"),
					icon: "rotate-ccw",
					position: "bottom-center",
					iconClasses: "text-amber-500",
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
		}
	)
}
</script>
