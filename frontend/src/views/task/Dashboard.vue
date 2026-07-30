<template>
	<BaseLayout :pageTitle="__('My Tasks')" back>
		<template #body>
			<div class="flex flex-col mt-5 mb-7 px-4 py-2 gap-5">
				<!-- Summary tiles -->
				<div class="grid grid-cols-4 gap-2">
					<SummaryTile
						:value="summary.due_today"
						:label="__('Due Today')"
						color="text-gray-900"
					/>
					<SummaryTile
						:value="summary.adhoc_open"
						:label="__('Ad-hoc')"
						color="text-indigo-600"
					/>
					<SummaryTile
						:value="summary.overdue"
						:label="__('Overdue')"
						color="text-red-600"
					/>
					<SummaryTile
						:value="summary.completed_this_week"
						:label="__('Done')"
						color="text-green-600"
					/>
				</div>

				<!-- Always-visible primary action: self-assign or assign to team -->
				<button
					class="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-indigo-600 text-white text-sm font-medium active:scale-[0.99]"
					@click="$router.push({ name: 'AssignTeamTask' })"
				>
					<FeatherIcon name="plus" class="h-4 w-4" />
					{{ __("Add Task") }}
				</button>

				<EmptyState
					v-if="myTasksDashboard.loading && !myTasksDashboard.data"
					:message="__('Loading your tasks...')"
				/>

				<!-- KPI scorecard — target vs actual, live between appraisals -->
				<div v-if="scorecard.length" class="flex flex-col gap-2">
					<div class="text-sm font-semibold text-gray-800">{{ __("Scorecard") }}</div>
					<div
						v-for="c in scorecard"
						:key="c.task_template"
						class="bg-white rounded-lg border border-gray-100 p-3 flex flex-col gap-1"
					>
						<div class="flex flex-row items-center justify-between">
							<span class="text-sm text-gray-800 truncate">{{ c.task_name }}</span>
							<span
								class="text-sm font-semibold"
								:class="(c.achievement_pct||0) >= 90 ? 'text-green-600' : (c.achievement_pct||0) >= 70 ? 'text-amber-600' : 'text-red-600'"
							>{{ Math.round(c.achievement_pct || 0) }}%</span>
						</div>
						<div class="flex flex-row items-center justify-between text-xs text-gray-500">
							<span>{{ __("Actual") }} {{ c.actual_value }} / {{ __("Target") }} {{ c.target_value }} {{ c.measurement_unit || "" }}</span>
							<span>{{ c.period_label }}</span>
						</div>
						<div class="h-1.5 rounded-full bg-gray-100 overflow-hidden">
							<div
								class="h-full rounded-full"
								:class="(c.achievement_pct||0) >= 90 ? 'bg-green-500' : (c.achievement_pct||0) >= 70 ? 'bg-amber-500' : 'bg-red-500'"
								:style="{ width: Math.min(100, Math.max(2, c.achievement_pct || 0)) + '%' }"
							/>
						</div>
					</div>
				</div>

				<!-- Stacked sections — partitioned so a task appears in exactly one bucket -->
				<TaskSection
					:title="__('Overdue')"
					:tasks="overdue"
					indicator="red"
					empty-hint=""
				/>
				<TaskSection
					:title="__('Today')"
					:tasks="today"
					indicator="amber"
					empty-hint=""
				/>
				<TaskSection
					:title="__('Ad-hoc')"
					:subtitle="__('One-off tasks you or your manager added')"
					:tasks="adhoc"
					indicator="indigo"
					empty-hint=""
				/>
				<TaskSection
					:title="__('Upcoming')"
					:tasks="upcoming"
					indicator="gray"
					empty-hint=""
					:collapsible="true"
				/>
				<TaskSection
					:title="__('Done This Week')"
					:tasks="completedWeek"
					indicator="green"
					empty-hint=""
					:collapsible="true"
				/>

				<EmptyState
					v-if="
						!myTasksDashboard.loading &&
						!overdue.length &&
						!today.length &&
						!adhoc.length &&
						!upcoming.length &&
						!completedWeek.length
					"
					:message="__('No tasks here. Tap “Add Task” to capture one for yourself or your team.')"
				/>
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { computed, h, inject, onMounted, onBeforeUnmount } from "vue"
import { FeatherIcon } from "frappe-ui"

const socket = inject("$socket")

import BaseLayout from "@/components/BaseLayout.vue"
import EmptyState from "@/components/EmptyState.vue"
import TaskCard from "@/components/TaskCard.vue"

import { myTasksDashboard, myScorecard } from "@/data/tasks"

// --- Small inline components -------------------------------------------------

const SummaryTile = (props) =>
	h("div", { class: "flex flex-col gap-1 bg-white rounded p-3 items-center" }, [
		h("span", { class: `text-2xl font-bold ${props.color}` }, props.value ?? 0),
		h("span", { class: "text-xs text-gray-500 text-center" }, props.label),
	])
SummaryTile.props = ["value", "label", "color"]

const INDICATOR_DOT = {
	red: "bg-red-500",
	amber: "bg-amber-500",
	indigo: "bg-indigo-500",
	gray: "bg-gray-400",
	green: "bg-green-500",
}

function TaskSection(props) {
	if (!props.tasks?.length) return null
	const dot = INDICATOR_DOT[props.indicator] || "bg-gray-400"
	const header = h(
		"div",
		{ class: "flex items-center gap-2 mt-2 mb-1" },
		[
			h("span", { class: `inline-block h-2 w-2 rounded-full ${dot}` }),
			h("h3", { class: "text-base font-semibold text-gray-900" }, props.title),
			h("span", { class: "text-sm text-gray-500" }, `(${props.tasks.length})`),
		]
	)
	const subtitle = props.subtitle
		? h("p", { class: "text-xs text-gray-500 -mt-1 mb-1" }, props.subtitle)
		: null
	const list = h(
		"div",
		{ class: "flex flex-col gap-2" },
		props.tasks.map((t) => h(TaskCard, { task: t, key: t.name }))
	)
	if (!props.collapsible) {
		return h("div", { class: "flex flex-col gap-1" }, [header, subtitle, list])
	}
	// <details> gives a free a11y-friendly expander.
	return h(
		"details",
		{ class: "flex flex-col gap-1" },
		[
			h("summary", { class: "cursor-pointer list-none" }, [header, subtitle]),
			list,
		]
	)
}
TaskSection.props = ["title", "subtitle", "tasks", "indicator", "emptyHint", "collapsible"]

// --- State -----------------------------------------------------------------

const data = computed(() => myTasksDashboard.data || {})
const scorecard = computed(() => myScorecard.data || [])
const summary = computed(() => data.value.summary || {})
const today = computed(() => data.value.today || [])
const adhoc = computed(() => data.value.adhoc || [])
const upcoming = computed(() => data.value.upcoming || [])
const overdue = computed(() => data.value.overdue || [])
const completedWeek = computed(() => data.value.completed_week || [])

// Goal is the only doctype that lands new tasks here (Task Instance = Goal).
// Subscribing makes externally-created tasks (scheduler, manager, etc.) show
// up live; the backend's refetch_resource push covers PWA-initiated changes.
function onGoalUpdate(d) {
	if (d?.doctype === "Goal") myTasksDashboard.reload()
}
onMounted(() => {
	socket.emit("doctype_subscribe", "Goal")
	socket.on("list_update", onGoalUpdate)
})
onBeforeUnmount(() => {
	socket.emit("doctype_unsubscribe", "Goal")
	socket.off("list_update", onGoalUpdate)
})
</script>
