<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="w-full sm:max-w-3xl sm:mx-auto bg-white px-4 py-3 border-b flex items-center gap-2">
				<button @click="router.back()" class="p-1 text-gray-500">
					<FeatherIcon name="arrow-left" class="h-5 w-5" />
				</button>
				<h1 class="text-lg font-semibold text-gray-800">{{ __("My Department") }}</h1>
			</div>
		</ion-header>

		<ion-content>
			<div class="w-full sm:max-w-3xl sm:mx-auto p-4 flex flex-col gap-4">
				<EmptyState
					v-if="!loading && !departments.length"
					:title="__('No department to manage')"
					:message="__('You are not set as the head of any department.')"
				/>

				<div
					v-for="d in departments"
					:key="d.department"
					class="bg-white rounded-lg border border-gray-100 p-4 flex flex-col gap-3"
				>
					<div class="flex flex-row items-center justify-between">
						<span class="font-semibold text-gray-800">{{ d.label }}</span>
						<span v-if="d.is_head" class="text-xs text-green-600">{{ __("You lead this") }}</span>
					</div>

					<div v-if="!d.members.length" class="text-sm text-gray-400">
						{{ __("No other members.") }}
					</div>

					<div
						v-for="m in d.members"
						:key="m.name"
						class="flex flex-row items-center justify-between gap-2 border-t border-gray-50 pt-2"
					>
						<div class="flex flex-col">
							<span class="text-sm text-gray-800">{{ m.employee_name }}</span>
							<span class="text-xs text-gray-400">{{ m.designation || m.name }}</span>
						</div>
						<FormControl
							type="select"
							:options="managerOptions(d, m)"
							:model-value="m.reports_to || ''"
							@update:model-value="(val) => repoint(m, val)"
							:disabled="saving === m.name"
						/>
					</div>
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { inject, computed, ref } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonHeader, IonContent } from "@ionic/vue"
import { FormControl, FeatherIcon, toast } from "frappe-ui"
import EmptyState from "@/components/EmptyState.vue"
import { myDepartment, setReportsTo } from "@/data/department"

const __ = inject("$translate")
const router = useRouter()
const saving = ref(null)

const loading = computed(() => myDepartment.loading)
const departments = computed(() => myDepartment.data?.departments || [])

// Eligible managers for a member: the head (caller) and the department's other
// members — never the member themselves (the server rejects a self-cycle too).
function managerOptions(d, member) {
	const opts = [{ label: __("— no manager —"), value: "" }]
	// Only offer "Me (head)" when the caller actually heads this department — an
	// HR viewer isn't the head, so labelling them so would be misleading.
	if (d.is_head && myDepartment.data?.caller && myDepartment.data.caller !== member.name)
		opts.push({ label: __("Me (head)"), value: myDepartment.data.caller })
	for (const other of d.members) {
		if (other.name !== member.name)
			opts.push({ label: other.employee_name, value: other.name })
	}
	return opts
}

async function repoint(member, newManager) {
	if ((member.reports_to || "") === (newManager || "")) return
	saving.value = member.name
	try {
		await setReportsTo(member.name, newManager)
		toast.success(__("Reporting line updated"))
	} catch (e) {
		toast.error(e?.messages?.[0] || __("Could not update"))
	} finally {
		saving.value = null
	}
}
</script>
