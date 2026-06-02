<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="w-full sm:max-w-3xl sm:mx-auto">
				<div class="flex flex-row bg-white shadow-sm py-4 px-3 items-center border-b">
					<Button variant="ghost" class="!px-1 mr-1 hover:bg-white" @click="router.back()">
						<FeatherIcon name="chevron-left" class="h-5 w-5" />
					</Button>
					<h2 class="text-xl font-semibold text-gray-900 truncate">{{ __("Tax Declaration") }}</h2>
				</div>
			</div>
		</ion-header>

		<ion-content>
			<div class="min-h-full bg-gray-50">
				<div class="w-full sm:max-w-3xl sm:mx-auto p-4 flex flex-col gap-4 pb-28">
					<p class="text-xs text-gray-500">
						<template v-if="data.payroll_period">
							{{ __("Period") }}: <b>{{ data.payroll_period }}</b>
							<span v-if="data.period_start">({{ data.period_start }} – {{ data.period_end }})</span>
						</template>
						<span v-else class="text-amber-600">{{ __("No active payroll period — ask HR to set one up.") }}</span>
						<span v-if="!editable" class="ml-2 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-600">{{ __("Submitted") }}</span>
					</p>

					<!-- ===== Regime comparator ===== -->
					<div class="bg-white rounded-xl border border-gray-100 p-4">
						<h3 class="text-base font-semibold text-gray-900 mb-3">{{ __("Old vs New Regime") }}</h3>
						<div class="grid grid-cols-2 gap-3">
							<FormControl type="number" :label="__('Annual Income (₹)')" v-model.number="annualIncome" />
							<FormControl type="number" :label="__('Total Deductions (₹)')" v-model.number="deductions" />
						</div>
						<Button variant="solid" class="w-full mt-3" :loading="compareRegimes.loading" @click="runCompare">
							{{ __("Compare Regimes") }}
						</Button>

						<div v-if="result" class="grid grid-cols-2 gap-3 mt-4">
							<div
								v-for="r in regimeCards"
								:key="r.key"
								:class="['rounded-xl p-3 border', r.recommended ? 'bg-emerald-50 border-emerald-200' : 'bg-gray-50 border-gray-100']"
							>
								<div class="flex items-center justify-between">
									<span class="text-xs font-semibold uppercase tracking-wide text-gray-600">{{ r.title }}</span>
									<span v-if="r.recommended" class="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-600 text-white">{{ __("Best") }}</span>
								</div>
								<div class="text-2xl font-bold text-gray-900 mt-1">{{ fmt(r.tax) }}</div>
								<div class="text-xs text-gray-500 mt-1">{{ __("Taxable") }}: {{ fmt(r.taxable) }}</div>
							</div>
						</div>
						<p v-if="result" class="text-sm text-center mt-3 text-emerald-700 font-medium">
							{{ __("{0} Regime saves you {1}/year", [result.recommended, fmt(result.savings)]) }}
						</p>
					</div>

					<!-- ===== Declaration ===== -->
					<div class="bg-white rounded-xl border border-gray-100 p-4">
						<h3 class="text-base font-semibold text-gray-900 mb-1">{{ __("Investment Declaration") }}</h3>
						<p class="text-xs text-gray-500 mb-3">{{ __("Declare investments for old-regime tax exemptions (80C, 80D, HRA, etc).") }}</p>

						<div v-for="(subs, category) in grouped" :key="category" class="mb-4">
							<div class="text-xs font-semibold text-indigo-600 uppercase tracking-wide mb-2">{{ category }}</div>
							<div v-for="s in subs" :key="s.name" class="flex items-center gap-2 mb-2">
								<span class="flex-1 text-sm text-gray-700">{{ s.name }}</span>
								<input
									type="number"
									class="w-32 text-right border border-gray-200 rounded-md px-2 py-1 text-sm"
									:placeholder="s.max_amount ? '≤ ' + s.max_amount : '0'"
									v-model.number="amounts[s.name]"
									:disabled="!editable"
								/>
							</div>
						</div>

						<div class="flex items-center justify-between pt-2 border-t mt-2">
							<span class="text-sm text-gray-600">{{ __("Total Declared") }}</span>
							<span class="text-lg font-bold text-gray-900">{{ fmt(totalDeclared) }}</span>
						</div>

						<div v-if="editable" class="flex gap-2 mt-4">
							<Button variant="subtle" class="flex-1 py-4" :loading="saveTaxDeclaration.loading" @click="save(0)">
								{{ __("Save Draft") }}
							</Button>
							<Button variant="solid" class="flex-1 py-4" :loading="saveTaxDeclaration.loading" @click="save(1)">
								{{ __("Submit") }}
							</Button>
						</div>
						<p v-else class="text-xs text-gray-400 mt-3">{{ __("Submitted — contact HR to revise.") }}</p>
					</div>
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { computed, inject, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonHeader, IonContent } from "@ionic/vue"
import { Button, FormControl, FeatherIcon, toast } from "frappe-ui"

import { myTaxDeclaration, saveTaxDeclaration, compareRegimes } from "@/data/taxDeclaration"

const __ = inject("$translate")
const router = useRouter()

myTaxDeclaration.fetch()

const data = computed(() => myTaxDeclaration.data || {})
const editable = computed(() => data.value.editable !== false)
const amounts = reactive({})
const annualIncome = ref(0)
const deductions = ref(0)
const result = ref(null)

watch(
	() => myTaxDeclaration.data,
	(d) => {
		if (!d) return
		;(d.rows || []).forEach((r) => {
			amounts[r.exemption_sub_category] = r.amount
		})
		if (!annualIncome.value) annualIncome.value = d.projected_annual_income || 0
	},
	{ immediate: true }
)

const grouped = computed(() => {
	const g = {}
	;(data.value.sub_categories || []).forEach((s) => {
		;(g[s.exemption_category || __("Other")] ||= []).push(s)
	})
	return g
})

const totalDeclared = computed(() =>
	Object.values(amounts).reduce((sum, v) => sum + (Number(v) || 0), 0)
)

const regimeCards = computed(() => {
	if (!result.value) return []
	return [
		{ key: "old", title: __("Old Regime"), tax: result.value.old.tax, taxable: result.value.old.taxable, recommended: result.value.recommended === "Old" },
		{ key: "new", title: __("New Regime"), tax: result.value.new.tax, taxable: result.value.new.taxable, recommended: result.value.recommended === "New" },
	]
})

const fmt = (v) =>
	"₹" + Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })

function runCompare() {
	if (!deductions.value) deductions.value = totalDeclared.value
	compareRegimes.submit(
		{ annual_income: annualIncome.value || 0, total_deductions: deductions.value || 0 },
		{
			onSuccess: (r) => (result.value = r),
			onError: (e) => toast({ title: __("Error"), text: __(e?.messages?.[0] || e.message), icon: "alert-circle", iconClasses: "text-red-500", position: "bottom-center" }),
		}
	)
}

function save(submit) {
	const rows = Object.entries(amounts)
		.filter(([, amt]) => Number(amt) > 0)
		.map(([exemption_sub_category, amount]) => ({ exemption_sub_category, amount: Number(amount) }))
	saveTaxDeclaration.submit(
		{ declarations: rows, submit },
		{
			onSuccess: () => {
				toast({ title: __("Saved"), text: submit ? __("Declaration submitted") : __("Draft saved"), icon: "check-circle", iconClasses: "text-green-500", position: "bottom-center" })
				myTaxDeclaration.reload()
			},
			onError: (e) => toast({ title: __("Error"), text: __(e?.messages?.[0] || e.message), icon: "alert-circle", iconClasses: "text-red-500", position: "bottom-center" }),
		}
	)
}
</script>
