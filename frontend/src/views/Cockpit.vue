<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="bg-white border-b border-gray-100">
				<div class="mx-auto w-full max-w-6xl flex items-center justify-between px-4 py-3">
					<div class="flex items-center gap-2">
						<button class="p-1 -ml-1 text-gray-600" @click="goHome">
							<FeatherIcon name="arrow-left" class="h-5 w-5" />
						</button>
						<div class="flex flex-col">
							<h2 class="text-lg font-bold text-gray-900 leading-tight">{{ __("HR Cockpit") }}</h2>
							<span v-if="data?.company" class="text-xs text-gray-500 leading-tight">{{ data.company }}</span>
						</div>
					</div>
					<div class="flex items-center gap-1">
						<button
							class="flex items-center gap-1 px-2 py-1 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-full"
							@click="$router.push({ name: 'ManageKraTasks' })"
						>
							<FeatherIcon name="target" class="h-4 w-4" />
							{{ __("KRAs & Tasks") }}
						</button>
						<button
							class="flex items-center gap-1 px-2 py-1 text-xs font-medium text-violet-600 bg-violet-50 rounded-full"
							@click="$router.push({ name: 'OrgChart3D' })"
						>
							<FeatherIcon name="box" class="h-4 w-4" />
							{{ __("3D Org Chart") }}
						</button>
						<button class="p-1 text-gray-500" @click="refresh">
							<FeatherIcon name="refresh-cw" class="h-5 w-5" :class="{ 'animate-spin': cockpit.loading }" />
						</button>
					</div>
				</div>
			</div>
		</ion-header>

		<ion-content>
			<div class="min-h-full bg-gray-50">
				<div class="mx-auto w-full max-w-6xl p-4 flex flex-col gap-4 pb-16">
					<!-- Period toggle -->
					<div class="flex items-center justify-between">
						<p class="text-xs text-gray-500">{{ __("As of") }} {{ data?.as_of }}</p>
						<div class="inline-flex rounded-full bg-white border border-gray-200 p-0.5">
							<button
								v-for="p in periods"
								:key="p"
								@click="changePeriod(p)"
								:class="[
									'px-3 py-1 text-xs font-medium rounded-full transition',
									period === p ? 'bg-indigo-600 text-white shadow' : 'text-gray-600',
								]"
							>
								{{ __(p) }}
							</button>
						</div>
					</div>

					<!-- 1. KPI hero (glass) -->
					<GlassCard variant="glass">
						<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
							<div
								v-for="k in data?.kpis || []"
								:key="k.key"
								class="flex flex-col items-start gap-1 rounded-xl bg-gray-50 p-3"
							>
								<div :class="['flex items-center justify-center h-8 w-8 rounded-lg', toneBg(k.tone)]">
									<FeatherIcon :name="k.icon" :class="['h-4 w-4', toneText(k.tone)]" />
								</div>
								<span class="text-2xl font-bold text-gray-900 leading-none mt-1">{{ k.value }}</span>
								<span class="text-xs text-gray-500 leading-tight">{{ k.label }}</span>
							</div>
						</div>
					</GlassCard>

					<!-- responsive grid for the panels -->
					<div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
						<!-- 2. Compliance & Documents -->
						<GlassCard :title="__('Compliance & Documents')" class="lg:col-span-2">
							<div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
								<div
									v-for="b in complianceBuckets"
									:key="b.key"
									:class="['rounded-xl p-3 border', b.box]"
								>
									<div class="flex items-center justify-between">
										<span :class="['text-xs font-semibold uppercase tracking-wide', b.text]">{{ b.title }}</span>
										<span :class="['text-2xl font-bold', b.text]">{{ b.total }}</span>
									</div>
									<ul class="mt-2 space-y-1">
										<li
											v-for="item in b.items"
											:key="item.label"
											class="flex items-center justify-between text-sm text-gray-600"
										>
											<span>{{ item.label }}</span>
											<span class="font-medium text-gray-800">{{ item.count }}</span>
										</li>
									</ul>
								</div>
							</div>
						</GlassCard>

						<!-- 3. My Actions -->
						<GlassCard :title="__('My Actions')">
							<ul class="flex flex-col divide-y divide-gray-100">
								<li v-for="a in data?.actions || []" :key="a.label">
									<button
										class="w-full flex items-center gap-3 py-2.5 text-left active:scale-[0.99] transition"
										@click="go(a.route)"
									>
										<span :class="['flex items-center justify-center h-9 w-9 rounded-lg shrink-0', toneBg(a.tone)]">
											<FeatherIcon :name="a.icon" :class="['h-4 w-4', toneText(a.tone)]" />
										</span>
										<span class="flex-1 text-sm text-gray-700">{{ a.label }}</span>
										<span
											:class="[
												'min-w-6 h-6 px-1.5 inline-flex items-center justify-center rounded-full text-xs font-bold',
												a.count ? toneBg(a.tone) + ' ' + toneText(a.tone) : 'bg-gray-100 text-gray-400',
											]"
										>
											{{ a.count }}
										</span>
										<FeatherIcon name="chevron-right" class="h-4 w-4 text-gray-300" />
									</button>
								</li>
							</ul>
						</GlassCard>
					</div>

					<!-- Employee Readiness -->
					<GlassCard v-if="readiness.total" :title="__('Employee Setup Readiness')">
						<div class="flex items-center gap-4">
							<div class="flex flex-col">
								<span class="text-3xl font-bold text-gray-900 leading-none">{{ readiness.ready }}<span class="text-base text-gray-400">/{{ readiness.total }}</span></span>
								<span class="text-xs text-gray-500 mt-1">{{ __("fully set up") }}</span>
							</div>
							<div class="flex-1">
								<div class="h-2 rounded-full bg-gray-100 overflow-hidden">
									<div class="h-full bg-emerald-500" :style="{ width: readiness.pct + '%' }" />
								</div>
								<span class="text-xs text-gray-500 mt-1 inline-block">{{ readiness.pct }}% {{ __("ready") }} · {{ readiness.incomplete }} {{ __("need attention") }}</span>
							</div>
						</div>
						<div class="flex flex-wrap gap-2 mt-3">
							<span
								v-for="(count, label) in missingChips"
								:key="label"
								class="text-xs px-2 py-1 rounded-full bg-red-50 text-red-600"
							>
								{{ label }}: {{ count }}
							</span>
							<span v-if="!hasMissing" class="text-xs text-emerald-600">
								{{ __("All set 🎉") }}
							</span>
						</div>
					</GlassCard>

					<!-- Task Coverage (governance gaps) -->
					<GlassCard :title="__('Task Coverage')">
						<template #header>
							<button
								class="text-xs font-medium text-indigo-600"
								@click="$router.push({ name: 'ManageKraTasks' })"
							>
								{{ __("Manage") }} →
							</button>
						</template>
						<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
							<button
								class="rounded-xl p-3 border text-left active:scale-[0.99] transition"
								:class="coverage.uncovered_kras?.length ? 'bg-amber-50 border-amber-100' : 'bg-emerald-50 border-emerald-100'"
								@click="$router.push({ name: 'ManageKraTasks' })"
							>
								<div class="flex items-center justify-between">
									<span class="text-xs font-semibold uppercase tracking-wide" :class="coverage.uncovered_kras?.length ? 'text-amber-600' : 'text-emerald-600'">
										{{ __("KRAs without tasks") }}
									</span>
									<span class="text-2xl font-bold" :class="coverage.uncovered_kras?.length ? 'text-amber-600' : 'text-emerald-600'">
										{{ coverage.totals?.uncovered_kras ?? 0 }}
									</span>
								</div>
								<ul v-if="coverage.uncovered_kras?.length" class="mt-2 space-y-1">
									<li v-for="k in coverage.uncovered_kras.slice(0, 4)" :key="k.name" class="text-sm text-gray-600 truncate">
										{{ k.title }}
									</li>
									<li v-if="coverage.uncovered_kras.length > 4" class="text-xs text-gray-400">
										+{{ coverage.uncovered_kras.length - 4 }} {{ __("more") }}
									</li>
								</ul>
								<p v-else class="mt-2 text-sm text-emerald-600">{{ __("Every active KRA has a task ✓") }}</p>
							</button>

							<button
								class="rounded-xl p-3 border text-left active:scale-[0.99] transition"
								:class="coverage.unassigned_tasks?.length ? 'bg-red-50 border-red-100' : 'bg-emerald-50 border-emerald-100'"
								@click="$router.push({ name: 'ManageKraTasks' })"
							>
								<div class="flex items-center justify-between">
									<span class="text-xs font-semibold uppercase tracking-wide" :class="coverage.unassigned_tasks?.length ? 'text-red-600' : 'text-emerald-600'">
										{{ __("Tasks assigned to nobody") }}
									</span>
									<span class="text-2xl font-bold" :class="coverage.unassigned_tasks?.length ? 'text-red-600' : 'text-emerald-600'">
										{{ coverage.totals?.unassigned_tasks ?? 0 }}
									</span>
								</div>
								<ul v-if="coverage.unassigned_tasks?.length" class="mt-2 space-y-1">
									<li v-for="t in coverage.unassigned_tasks.slice(0, 4)" :key="t.name" class="text-sm text-gray-600 truncate">
										{{ t.task_name }}
									</li>
									<li v-if="coverage.unassigned_tasks.length > 4" class="text-xs text-gray-400">
										+{{ coverage.unassigned_tasks.length - 4 }} {{ __("more") }}
									</li>
								</ul>
								<p v-else class="mt-2 text-sm text-emerald-600">{{ __("Every active task reaches someone ✓") }}</p>
							</button>
						</div>
					</GlassCard>

					<div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
						<!-- 4. People Pulse -->
						<GlassCard :title="__('People Pulse')">
							<div class="grid grid-cols-3 gap-3">
								<div v-for="p in data?.people || []" :key="p.label" class="flex flex-col items-center text-center gap-1">
									<span :class="['flex items-center justify-center h-10 w-10 rounded-full', toneBg(p.tone)]">
										<FeatherIcon :name="p.icon" :class="['h-5 w-5', toneText(p.tone)]" />
									</span>
									<span class="text-xl font-bold text-gray-900">{{ p.count }}</span>
									<span class="text-xs text-gray-500 leading-tight">{{ p.label }}</span>
								</div>
							</div>
						</GlassCard>

						<!-- 5. Trends -->
						<GlassCard :title="__('Trends')" class="lg:col-span-2">
							<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
								<div v-for="t in trendList" :key="t.key">
									<div class="flex items-center justify-between mb-1">
										<span class="text-xs text-gray-500">{{ t.label }}</span>
										<span class="text-xs font-semibold text-gray-700">
											{{ t.points?.[t.points.length - 1] ?? 0 }}
										</span>
									</div>
									<Sparkline :points="t.points || []" :color="t.color" />
									<div class="flex justify-between mt-1">
										<span v-for="(lab, i) in t.labels || []" :key="i" class="text-[10px] text-gray-400">{{ lab }}</span>
									</div>
								</div>
							</div>
						</GlassCard>
					</div>

					<p v-if="cockpit.error" class="text-center text-sm text-red-500">
						{{ __("Could not load the cockpit. Pull to refresh.") }}
					</p>
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { computed, inject } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonHeader, IonContent } from "@ionic/vue"
import { FeatherIcon } from "frappe-ui"

import GlassCard from "@/components/cockpit/GlassCard.vue"
import Sparkline from "@/components/cockpit/Sparkline.vue"
import { cockpit, setCockpitPeriod } from "@/data/cockpit"

const __ = inject("$translate")
const router = useRouter()

const periods = ["Daily", "Weekly", "Monthly"]
const data = computed(() => cockpit.data || {})
const period = computed(() => data.value?.period || "Monthly")

const TONES = {
	brand: ["bg-indigo-100", "text-indigo-600"],
	green: ["bg-emerald-100", "text-emerald-600"],
	amber: ["bg-amber-100", "text-amber-600"],
	red: ["bg-red-100", "text-red-600"],
	violet: ["bg-violet-100", "text-violet-600"],
	blue: ["bg-sky-100", "text-sky-600"],
	grey: ["bg-gray-100", "text-gray-500"],
}
const toneBg = (t) => (TONES[t] || TONES.grey)[0]
const toneText = (t) => (TONES[t] || TONES.grey)[1]

const complianceBuckets = computed(() => {
	const c = data.value?.compliance || {}
	const t = c.totals || {}
	return [
		{ key: "overdue", title: __("Overdue"), total: t.overdue ?? 0, items: c.overdue || [], box: "bg-red-50 border-red-100", text: "text-red-600" },
		{ key: "due_soon", title: __("Due Soon"), total: t.due_soon ?? 0, items: c.due_soon || [], box: "bg-amber-50 border-amber-100", text: "text-amber-600" },
		{ key: "done", title: __("Done"), total: t.done ?? 0, items: c.done || [], box: "bg-emerald-50 border-emerald-100", text: "text-emerald-600" },
	]
})

const coverage = computed(() => data.value?.coverage || {})
const readiness = computed(() => data.value?.readiness || {})
const missingChips = computed(() => {
	const m = readiness.value?.missing || {}
	return Object.fromEntries(Object.entries(m).filter(([, v]) => v > 0))
})
const hasMissing = computed(() => Object.keys(missingChips.value).length > 0)

const trendList = computed(() => {
	const tr = data.value?.trends || {}
	return [
		{ key: "joiners", ...(tr.joiners || {}), color: "#6366f1" },
		{ key: "on_leave", ...(tr.on_leave || {}), color: "#f59e0b" },
	]
})

function changePeriod(p) {
	if (p !== period.value) setCockpitPeriod(p)
}
function refresh() {
	cockpit.reload()
}
function go(routeName) {
	if (routeName) router.push({ name: routeName }).catch(() => {})
}
function goHome() {
	router.push({ name: "Home" })
}
</script>
