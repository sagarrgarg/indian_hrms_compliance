<template>
	<ion-page>
		<ion-content :fullscreen="true">
			<div class="flex flex-col gap-4 p-4">
				<div class="flex flex-col gap-1">
					<h1 class="text-lg font-semibold text-gray-900">{{ __("Request a Grant") }}</h1>
					<span class="text-sm text-gray-500">
						{{ __("Incentive, retention bonus, or ad-hoc additional salary. Goes to HR for approval (or to your manager if it's for an HR person).") }}
					</span>
				</div>

				<FormControl
					type="select"
					:label="__('Grant Type')"
					:options="grantTypeOptions"
					v-model="form.grant_type"
				/>

				<FormControl
					type="autocomplete"
					:label="__('Employee')"
					:options="employeeOptions"
					:modelValue="selectedEmployee"
					@update:modelValue="(v) => (selectedEmployee = v)"
					:placeholder="__('Select an employee')"
				/>

				<FormControl type="select" :label="__('What to grant')" :options="modeOptions" v-model="mode" />

				<template v-if="mode === 'amount'">
					<FormControl
						type="autocomplete"
						:label="__('Salary Component')"
						:options="componentOptions"
						:modelValue="selectedComponent"
						@update:modelValue="(v) => (selectedComponent = v)"
						:placeholder="__('Select a component')"
					/>
					<FormControl type="number" :label="__('Amount')" v-model="form.amount" />
				</template>
				<template v-else>
					<FormControl
						type="number"
						:label="__('Grace Days (full-day increment)')"
						v-model="form.grace_days"
					/>
					<span class="text-xs text-gray-400">
						{{ __("Adds full paid days that scale every payment-days component.") }}
					</span>
				</template>

				<FormControl type="date" :label="__('Payroll Date')" v-model="form.payroll_date" />

				<Button
					variant="solid"
					:loading="requestGrant.loading"
					:disabled="!canSubmit"
					@click="onSubmit"
				>
					{{ __("Send for Approval") }}
				</Button>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { IonPage, IonContent } from "@ionic/vue"
import { ref, computed, onMounted } from "vue"
import { Button, FormControl, toast } from "frappe-ui"
import { useRouter } from "vue-router"

import { grantFormOptions, requestGrant } from "@/data/grants"

const router = useRouter()

const options = ref({ employees: [], components: [], grant_types: [] })
const mode = ref("amount")
const selectedEmployee = ref(null)
const selectedComponent = ref(null)
const form = ref({ grant_type: "Incentive", amount: 0, grace_days: 0, payroll_date: null })

onMounted(async () => {
	const data = await grantFormOptions.fetch()
	if (data) options.value = data
})

const grantTypeOptions = computed(() =>
	(options.value.grant_types || []).map((t) => ({ label: t, value: t })),
)
const employeeOptions = computed(() =>
	(options.value.employees || []).map((e) => ({ label: e.employee_name, value: e.name })),
)
const componentOptions = computed(() =>
	(options.value.components || []).map((c) => ({ label: c, value: c })),
)
const modeOptions = [
	{ label: __("Component + Amount"), value: "amount" },
	{ label: __("Grace Days (full day)"), value: "days" },
]

const canSubmit = computed(() => {
	if (!selectedEmployee.value?.value) return false
	if (mode.value === "amount")
		return !!selectedComponent.value?.value && Number(form.value.amount) > 0
	return Number(form.value.grace_days) > 0
})

async function onSubmit() {
	if (!canSubmit.value) return
	try {
		await requestGrant.submit({
			employee: selectedEmployee.value.value,
			grant_type: form.value.grant_type,
			salary_component: mode.value === "amount" ? selectedComponent.value.value : null,
			amount: mode.value === "amount" ? form.value.amount : 0,
			grace_days: mode.value === "days" ? form.value.grace_days : 0,
			payroll_date: form.value.payroll_date,
		})
		toast.success(__("Sent for approval"))
		router.back()
	} catch (e) {
		toast.error(e?.messages?.[0] || __("Could not submit the request"))
	}
}
</script>
