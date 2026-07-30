<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="bg-white border-b border-gray-100">
				<div class="mx-auto w-full max-w-4xl flex items-center justify-between px-4 py-3">
					<div class="flex items-center gap-2">
						<button class="p-1 -ml-1 text-gray-600" @click="onBack">
							<FeatherIcon name="arrow-left" class="h-5 w-5" />
						</button>
						<div class="flex flex-col">
							<h2 class="text-lg font-bold text-gray-900 leading-tight">{{ __("Manage KRAs & Tasks") }}</h2>
							<span v-if="options.company" class="text-xs text-gray-500 leading-tight">{{ options.company }}</span>
						</div>
					</div>
					<button
						v-if="!editing"
						class="flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-full"
						@click="newRecord"
					>
						<FeatherIcon name="plus" class="h-4 w-4" />
						{{ tab === "kra" ? __("New KRA") : __("New Task") }}
					</button>
				</div>
			</div>
		</ion-header>

		<ion-content>
			<div class="min-h-full bg-gray-50">
				<div class="mx-auto w-full max-w-4xl p-4 flex flex-col gap-4 pb-16">
					<!-- Tab toggle -->
					<div v-if="!editing" class="inline-flex self-start rounded-full bg-white border border-gray-200 p-0.5">
						<button
							v-for="t in tabs"
							:key="t.key"
							@click="tab = t.key"
							:class="[
								'px-4 py-1.5 text-sm font-medium rounded-full transition',
								tab === t.key ? 'bg-indigo-600 text-white shadow' : 'text-gray-600',
							]"
						>
							{{ t.label }}
						</button>
					</div>

					<!-- ===================== LIST MODE ===================== -->
					<template v-if="!editing">
						<!-- KRA list -->
						<div v-if="tab === 'kra'" class="flex flex-col gap-2">
							<p v-if="kraLoading" class="text-sm text-gray-400 text-center py-6">{{ __("Loading…") }}</p>
							<p v-else-if="!kras.length" class="text-sm text-gray-400 text-center py-6">
								{{ __("No KRAs yet. Create one to start building your task library.") }}
							</p>
							<div
								v-for="k in kras"
								:key="k.name"
								class="flex items-center gap-3 bg-white rounded-xl border border-gray-100 p-3"
							>
								<span class="h-2.5 w-2.5 rounded-full shrink-0" :style="{ backgroundColor: k.color || '#9ca3af' }" />
								<div class="flex-1 min-w-0">
									<div class="flex items-center gap-2">
										<span class="text-sm font-medium text-gray-900 truncate">{{ k.title }}</span>
										<span v-if="k.status !== 'Active'" class="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500">{{ k.status }}</span>
									</div>
									<span class="text-xs text-gray-500">
										{{ k.kra_category || __("Uncategorised") }} · {{ k.task_count || 0 }} {{ __("tasks") }}
									</span>
								</div>
								<button class="p-1.5 text-gray-400 hover:text-indigo-600" @click="editKra(k.name)">
									<FeatherIcon name="edit-2" class="h-4 w-4" />
								</button>
								<button class="p-1.5 text-gray-400 hover:text-red-600" @click="removeKra(k)">
									<FeatherIcon name="trash-2" class="h-4 w-4" />
								</button>
							</div>
						</div>

						<!-- Task list -->
						<div v-else class="flex flex-col gap-2">
							<p v-if="taskLoading" class="text-sm text-gray-400 text-center py-6">{{ __("Loading…") }}</p>
							<p v-else-if="!hrmsTasks.length" class="text-sm text-gray-400 text-center py-6">
								{{ __("No tasks yet. Create one and assign it to a designation or everyone.") }}
							</p>
							<div
								v-for="t in hrmsTasks"
								:key="t.name"
								class="flex items-center gap-3 bg-white rounded-xl border border-gray-100 p-3"
							>
								<div class="flex-1 min-w-0">
									<div class="flex items-center gap-2">
										<span class="text-sm font-medium text-gray-900 truncate">{{ t.task_name }}</span>
										<span
											:class="[
												'text-[10px] px-1.5 py-0.5 rounded-full',
												t.status === 'Active' ? 'bg-emerald-50 text-emerald-600' : 'bg-gray-100 text-gray-500',
											]"
										>{{ t.status }}</span>
									</div>
									<span class="text-xs text-gray-500">
											{{ t.kra }} · {{ t.use_cadence_schedule ? __("Scheduled") : t.frequency }}
											<span
												v-if="t.risk_tier && t.risk_tier !== 'Routine'"
												:class="[
													'ml-1 px-1.5 py-0.5 rounded-full text-[10px]',
													t.risk_tier === 'Critical'
														? 'bg-red-50 text-red-600'
														: 'bg-amber-50 text-amber-700',
												]"
											>{{ t.risk_tier }}</span>
										</span>
								</div>
								<button class="p-1.5 text-gray-400 hover:text-indigo-600" @click="editTask(t.name)">
									<FeatherIcon name="edit-2" class="h-4 w-4" />
								</button>
								<button class="p-1.5 text-gray-400 hover:text-red-600" @click="removeTask(t)">
									<FeatherIcon name="trash-2" class="h-4 w-4" />
								</button>
							</div>
						</div>
					</template>

					<!-- ===================== EDIT MODE: KRA ===================== -->
					<div v-else-if="tab === 'kra'" class="flex flex-col gap-4 bg-white rounded-xl border border-gray-100 p-4">
						<h3 class="text-base font-semibold text-gray-900">
							{{ kraForm.name ? __("Edit KRA") : __("New KRA") }}
						</h3>
						<FormControl type="text" :label="__('Title')" v-model="kraForm.title" />
						<FormControl type="select" :label="__('Category')" :options="categoryOptions" v-model="kraForm.kra_category" />
						<FormControl type="select" :label="__('Status')" :options="kraStatusOptions" v-model="kraForm.status" />
						<FormControl type="select" :label="__('Owner Designation')" :options="designationOptions" v-model="kraForm.owner_designation" />
						<div class="flex flex-col gap-1">
							<FormControl
								type="select"
								:label="__('DRI (Accountable Owner)')"
								:options="employeeOptions"
								v-model="kraForm.dri"
							/>
							<span class="text-xs text-gray-500">
								{{ __("The one person answerable for this KRA. Required while the KRA is Active.") }}
							</span>
						</div>
						<div class="flex flex-col gap-1">
							<FormControl
								type="select"
								:label="__('Acting DRI (optional cover)')"
								:options="employeeOptions"
								v-model="kraForm.acting_dri"
							/>
							<FormControl
								v-if="kraForm.acting_dri"
								type="date"
								:label="__('Acting Until')"
								v-model="kraForm.acting_until"
							/>
							<span class="text-xs text-gray-500">
								{{ __("Effective-dated stand-in while the DRI is on leave or the seat is interim-vacant.") }}
							</span>
						</div>
						<FormControl type="textarea" :label="__('Short Description')" v-model="kraForm.description" />
						<div class="flex gap-2 pt-2">
							<Button variant="solid" class="flex-1 py-4" :loading="saveKra.loading" :disabled="!kraCanSave" @click="submitKra">
								{{ __("Save") }}
							</Button>
							<Button variant="subtle" class="flex-1 py-4" @click="cancel">{{ __("Cancel") }}</Button>
						</div>
					</div>

					<!-- ===================== EDIT MODE: TASK ===================== -->
					<div v-else class="flex flex-col gap-4 bg-white rounded-xl border border-gray-100 p-4">
						<h3 class="text-base font-semibold text-gray-900">
							{{ taskForm.name ? __("Edit Task") : __("New Task") }}
						</h3>
						<FormControl type="text" :label="__('Task Name')" v-model="taskForm.task_name" />
						<FormControl type="select" :label="__('KRA')" :options="kraOptions" v-model="taskForm.kra" />
						<FormControl type="select" :label="__('Frequency')" :options="frequencyOptions" v-model="taskForm.frequency" />
						<FormControl type="select" :label="__('Completion Type')" :options="completionTypeOptions" v-model="taskForm.completion_type" />
						<div class="flex flex-col gap-1">
							<FormControl
								type="select"
								:label="__('Risk Tier')"
								:options="riskTierOptions"
								v-model="taskForm.risk_tier"
								:disabled="!!taskForm.is_statutory"
							/>
							<span class="text-xs text-gray-500">{{ tierHelp }}</span>
						</div>
						<div class="flex flex-col gap-1">
							<FormControl
								type="checkbox"
								:label="__('Statutory (born Critical)')"
								v-model="taskForm.is_statutory"
							/>
							<span class="text-xs text-gray-500">
								{{ __("Statutory / money-movement work is locked at Critical and can never be lowered.") }}
							</span>
						</div>
						<FormControl type="select" :label="__('Status')" :options="taskStatusOptions" v-model="taskForm.status" />
						<FormControl
							v-if="taskForm.status === 'Active'"
							type="date"
							:label="__('Effective From')"
							v-model="taskForm.effective_from"
						/>
						<FormControl
							type="checkbox"
							:label="__('Applicable to All Active Employees')"
							v-model="taskForm.applicable_to_all_active"
						/>
						<FormControl
							v-if="!taskForm.applicable_to_all_active"
							type="select"
							:label="__('Assign to Designation')"
							:options="designationOptions"
							v-model="taskForm.assigned_to_designation"
						/>
						<FormControl
							v-if="!taskForm.applicable_to_all_active"
							type="select"
							:label="__('Assign to Department')"
							:options="departmentOptions"
							v-model="taskForm.assigned_to_department"
						/>
						<FormControl type="textarea" :label="__('Description')" v-model="taskForm.description" />
						<div class="flex gap-2 pt-2">
							<Button variant="solid" class="flex-1 py-4" :loading="saveHrmsTask.loading" :disabled="!taskCanSave" @click="submitTask">
								{{ __("Save") }}
							</Button>
							<Button variant="subtle" class="flex-1 py-4" @click="cancel">{{ __("Cancel") }}</Button>
						</div>
					</div>
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { computed, inject, nextTick, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonHeader, IonContent } from "@ionic/vue"
import { Button, FormControl, FeatherIcon, toast } from "frappe-ui"

import {
	kraList,
	hrmsTaskList,
	formOptions,
	getKra,
	saveKra,
	deleteKra,
	getHrmsTask,
	saveHrmsTask,
	deleteHrmsTask,
} from "@/data/kraTasks"
import { cockpit } from "@/data/cockpit"

const __ = inject("$translate")
const router = useRouter()

kraList.fetch()
hrmsTaskList.fetch()
formOptions.fetch()

const tabs = [
	{ key: "kra", label: __("KRAs") },
	{ key: "task", label: __("Tasks") },
]
const tab = ref("kra")
const editing = ref(false)

const kras = computed(() => kraList.data || [])
const hrmsTasks = computed(() => hrmsTaskList.data || [])
const kraLoading = computed(() => kraList.loading)
const taskLoading = computed(() => hrmsTaskList.loading)
const options = computed(() => formOptions.data || {})

const toOpts = (arr, blank) => [
	...(blank ? [{ label: blank, value: "" }] : []),
	...(arr || []).map((v) => ({ label: v, value: v })),
]
const categoryOptions = computed(() => toOpts(options.value.kra_categories, __("Uncategorised")))
const kraStatusOptions = computed(() => toOpts(["Active", "Archived"]))
const taskStatusOptions = computed(() => toOpts(["Draft", "Active", "Paused", "Retired"]))
const frequencyOptions = computed(() => toOpts(options.value.frequencies))
const completionTypeOptions = computed(() => toOpts(options.value.completion_types))
const designationOptions = computed(() => toOpts(options.value.designations, __("— none —")))
const riskTierOptions = computed(() => toOpts(options.value.risk_tiers || ["Routine", "Standard", "Critical"]))
const employeeOptions = computed(() => [
	{ label: __("— none —"), value: "" },
	...(options.value.employees || []).map((e) => ({
		label: `${e.employee_name} (${e.name})`,
		value: e.name,
	})),
])
const tierHelp = computed(
	() =>
		({
			Routine: __("One tap to complete. No evidence, no approval."),
			Standard: __("Captures evidence — a file, a number, a note."),
			Critical: __("Evidence plus approval by someone other than the doer."),
		})[taskForm.risk_tier] || "",
)
const departmentOptions = computed(() => toOpts(options.value.departments, __("— none —")))
const kraOptions = computed(() => [
	{ label: __("Select a KRA"), value: "" },
	...(options.value.kras || []).map((k) => ({ label: k.title, value: k.name })),
])

const blankKra = () => ({
	name: "", title: "", kra_category: "", status: "Active", owner_designation: "", dri: "",
	acting_dri: "", acting_until: "", description: "",
})
const blankTask = () => ({
	name: "", task_name: "", kra: "", frequency: "Daily", completion_type: "Checkbox",
	risk_tier: "Routine", is_statutory: 0, status: "Draft", effective_from: "", applicable_to_all_active: 0,
	assigned_to_designation: "", assigned_to_department: "", description: "",
	// The tier is a label over these real controls. We MUST round-trip and send
	// them: if we don't, the server keeps the stored values and its upward
	// reconciliation snaps the tier straight back — so lowering a tier in the PWA
	// would silently do nothing. Presets applied by watch(taskForm.risk_tier).
	requires_approval: 0, requires_attachment: 0, approver_resolution: "Reports To",
})

// Same tier → controls mapping the Desk form uses (hrms_task.js TIER_PRESETS),
// so authoring a task is one decision. The server still enforces the Critical
// invariant independently; these presets are convenience.
const TIER_PRESETS = {
	Routine: { requires_attachment: 0, requires_approval: 0 },
	Standard: { requires_attachment: 1, requires_approval: 0 },
	Critical: { requires_attachment: 1, requires_approval: 1, approver_resolution: "Reports To" },
}
const kraForm = reactive(blankKra())
const taskForm = reactive(blankTask())

// Picking a tier presets its controls. Guarded by `applyingTierPreset` so the
// initial load from editTask() (which sets risk_tier to the stored value) does
// not clobber the task's real, possibly-customised controls.
let applyingTierPreset = false
watch(
	() => taskForm.risk_tier,
	(tier) => {
		if (applyingTierPreset) return
		const preset = TIER_PRESETS[tier]
		if (preset) Object.assign(taskForm, preset)
	},
)
// Statutory work is born Critical and locked there — mirror the server invariant.
watch(
	() => taskForm.is_statutory,
	(statutory) => {
		if (statutory) taskForm.risk_tier = "Critical"
	},
)

const taskCanSave = computed(
	() => !!taskForm.task_name && !!taskForm.kra && !(taskForm.status === "Active" && !taskForm.effective_from)
)
// A NEW Active KRA must name a DRI — gate here so the user sees why the button
// is disabled instead of hitting a server-side validation error. Existing KRAs
// that predate the field only warn server-side (kra.py _validate_dri), so we
// must NOT block re-saving them, or a legacy Active KRA with a blank DRI could
// never be edited at all.
const kraCanSave = computed(
	() => !!kraForm.title && !(!kraForm.name && kraForm.status === "Active" && !kraForm.dri)
)

function newRecord() {
	if (tab.value === "kra") Object.assign(kraForm, blankKra())
	else Object.assign(taskForm, blankTask())
	editing.value = true
}

function cancel() {
	editing.value = false
}
function onBack() {
	if (editing.value) editing.value = false
	else router.back()
}

async function editKra(name) {
	const doc = await getKra.fetch({ name })
	Object.assign(kraForm, blankKra(), {
		name: doc.name, title: doc.title, kra_category: doc.kra_category || "",
		status: doc.status, owner_designation: doc.owner_designation || "",
		dri: doc.dri || "", acting_dri: doc.acting_dri || "", acting_until: doc.acting_until || "",
		description: doc.description || "",
	})
	tab.value = "kra"
	editing.value = true
}

async function editTask(name) {
	const doc = await getHrmsTask.fetch({ name })
	// Suppress the tier-preset watch while we load: setting risk_tier here would
	// otherwise overwrite the task's real, stored controls with the tier default.
	applyingTierPreset = true
	Object.assign(taskForm, blankTask(), {
		name: doc.name, task_name: doc.task_name, kra: doc.kra, frequency: doc.frequency,
		completion_type: doc.completion_type, risk_tier: doc.risk_tier || "Routine",
		is_statutory: doc.is_statutory ? 1 : 0,
		status: doc.status, effective_from: doc.effective_from || "",
		applicable_to_all_active: doc.applicable_to_all_active ? 1 : 0,
		assigned_to_designation: doc.assigned_to_designation || "",
		assigned_to_department: doc.assigned_to_department || "", description: doc.description || "",
		requires_approval: doc.requires_approval ? 1 : 0,
		requires_attachment: doc.requires_attachment ? 1 : 0,
		approver_resolution: doc.approver_resolution || "Reports To",
	})
	await nextTick()
	applyingTierPreset = false
	tab.value = "task"
	editing.value = true
}

function ok(text) {
	toast({ title: __("Saved"), text, icon: "check-circle", position: "bottom-center", iconClasses: "text-green-500" })
}
function err(error) {
	toast({
		title: __("Error"),
		text: __(error?.messages?.[0] || error?.message || "Something went wrong"),
		icon: "alert-circle",
		position: "bottom-center",
		iconClasses: "text-red-500",
	})
}
function afterChange() {
	kraList.reload()
	hrmsTaskList.reload()
	formOptions.reload()
	cockpit.reload()
}

function submitKra() {
	saveKra.submit(
		{ values: { ...kraForm } },
		{
			onSuccess() { ok(__("KRA saved")); editing.value = false; afterChange() },
			onError: err,
		}
	)
}
function submitTask() {
	saveHrmsTask.submit(
		{ values: { ...taskForm } },
		{
			onSuccess() { ok(__("Task saved")); editing.value = false; afterChange() },
			onError: err,
		}
	)
}

function removeKra(k) {
	if (!window.confirm(__("Delete KRA '{0}'? This cannot be undone.", [k.title]))) return
	deleteKra.submit({ name: k.name }, { onSuccess() { ok(__("KRA deleted")); afterChange() }, onError: err })
}
function removeTask(t) {
	if (!window.confirm(__("Delete task '{0}'? This cannot be undone.", [t.task_name]))) return
	deleteHrmsTask.submit({ name: t.name }, { onSuccess() { ok(__("Task deleted")); afterChange() }, onError: err })
}
</script>
