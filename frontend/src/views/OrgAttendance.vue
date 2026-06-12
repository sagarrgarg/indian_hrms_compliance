<template>
	<BaseLayout :pageTitle="__('Org Attendance')" back>
		<template #body>
			<div class="flex flex-col mt-5 mb-7 px-4 py-2 gap-5">
				<!-- Date selector + summary -->
				<div class="flex items-end gap-2">
					<div class="flex-1">
						<label class="block text-[10px] uppercase tracking-wide text-gray-500 mb-1">{{ __("Date") }}</label>
						<input
							type="date"
							v-model="selectedDate"
							:max="todayIso"
							class="w-full border border-gray-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200"
						/>
					</div>
					<button
						class="px-3 py-2 rounded-md bg-gray-100 text-gray-700 text-sm"
						:disabled="orgAttendanceToday.loading"
						@click="reload"
					>
						<FeatherIcon name="refresh-cw" class="h-4 w-4" />
					</button>
				</div>

				<div class="text-[11px] text-gray-500 -mt-3">
					{{ isToday ? __("Live check-ins (today's Attendance is marked overnight)") : __("Marked Attendance for {0}", [selectedDate]) }}
				</div>

				<!-- Summary tiles — labels swap by mode -->
				<div class="grid grid-cols-4 gap-2">
					<template v-if="isToday">
						<SummaryTile :value="counts.in_now" :label="__('In')" color="text-green-700" />
						<SummaryTile :value="counts.out" :label="__('Out')" color="text-gray-700" />
						<SummaryTile :value="counts.on_leave" :label="__('Leave')" color="text-amber-700" />
						<SummaryTile :value="counts.not_yet_in" :label="__('Not in')" color="text-red-700" />
					</template>
					<template v-else>
						<SummaryTile :value="counts.present" :label="__('Present')" color="text-green-700" />
						<SummaryTile :value="counts.absent" :label="__('Absent')" color="text-red-700" />
						<SummaryTile :value="counts.on_leave" :label="__('Leave')" color="text-amber-700" />
						<SummaryTile :value="counts.not_marked" :label="__('Not Marked')" color="text-gray-700" />
					</template>
				</div>

				<div v-if="scope === 'none'" class="bg-amber-50 border border-amber-100 rounded-xl p-4 text-sm text-amber-900">
					{{ __("You don't have access to org-wide attendance. HR Managers see all; reporting managers see their direct reports.") }}
				</div>

				<!-- Search -->
				<div v-if="scope !== 'none'" class="flex items-center gap-2">
					<input
						v-model="query"
						type="text"
						:placeholder="__('Search name or department...')"
						class="flex-1 border border-gray-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200"
					/>
				</div>

				<EmptyState
					v-if="orgAttendanceToday.loading && !orgAttendanceToday.data"
					:message="__('Loading roll-call...')"
				/>

				<!-- Today mode sections -->
				<template v-if="scope !== 'none' && isToday">
					<AttendanceSection
						:title="__('In Now')"
						:people="filterPeople(data.in_now)"
						indicator="green"
						show-time-field="first_in"
					/>
					<AttendanceSection
						:title="__('Out for the day')"
						:people="filterPeople(data.out)"
						indicator="gray"
						show-time-field="last_time"
						:collapsible="true"
					/>
					<AttendanceSection
						:title="__('On Leave')"
						:people="filterPeople(data.on_leave)"
						indicator="amber"
						show-leave-type
					/>
					<AttendanceSection
						:title="__('Not Checked In')"
						:people="filterPeople(data.not_yet_in)"
						indicator="red"
						:collapsible="true"
					/>
				</template>

				<!-- Past-date mode sections -->
				<template v-if="scope !== 'none' && !isToday">
					<AttendanceSection
						:title="__('Present')"
						:people="filterPeople(data.present)"
						indicator="green"
						show-time-field="in_time"
					/>
					<AttendanceSection
						:title="__('On Leave')"
						:people="filterPeople(data.on_leave)"
						indicator="amber"
						show-leave-type
					/>
					<AttendanceSection
						:title="__('Absent')"
						:people="filterPeople(data.absent)"
						indicator="red"
					/>
					<AttendanceSection
						:title="__('Not Marked')"
						:people="filterPeople(data.not_marked)"
						indicator="gray"
						:collapsible="true"
					/>
				</template>

				<p class="text-[10px] text-gray-400 text-center mt-2">
					{{ __("As of {0}", [asOf]) }}
				</p>
			</div>
		</template>
	</BaseLayout>
</template>

<script setup>
import { computed, h, inject, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { FeatherIcon } from "frappe-ui"

import BaseLayout from "@/components/BaseLayout.vue"
import EmptyState from "@/components/EmptyState.vue"

import { orgAttendanceToday } from "@/data/orgAttendance"

const socket = inject("$socket")

const todayIso = new Date().toISOString().slice(0, 10)
const selectedDate = ref(todayIso)
const query = ref("")

const data = computed(() => orgAttendanceToday.data || {})
const counts = computed(() => data.value.counts || {})
const scope = computed(() => data.value.scope || "all")
const asOf = computed(() => data.value.as_of || "—")
const mode = computed(() => data.value.mode || "today")
const isToday = computed(() => mode.value === "today")

function reload() {
	orgAttendanceToday.update({ params: { for_date: selectedDate.value } })
	orgAttendanceToday.reload()
}

// Reload on date change. Also clear on first mount so the cache key sees the
// for_date arg from the start.
watch(selectedDate, reload, { immediate: true })

function filterPeople(arr) {
	const q = query.value.trim().toLowerCase()
	if (!q) return arr || []
	return (arr || []).filter((p) => {
		const hay = [p.employee_name, p.department, p.designation, p.company].filter(Boolean).join(" ").toLowerCase()
		return hay.includes(q)
	})
}

// --- inline render components ---

const SummaryTile = (props) =>
	h("div", { class: "flex flex-col gap-0.5 bg-white rounded p-3 items-center" }, [
		h("span", { class: `text-2xl font-bold ${props.color}` }, props.value ?? 0),
		h("span", { class: "text-xs text-gray-500 text-center" }, props.label),
	])
SummaryTile.props = ["value", "label", "color"]

const INDICATOR_DOT = {
	green: "bg-green-500",
	gray: "bg-gray-400",
	amber: "bg-amber-500",
	red: "bg-red-500",
}

function AttendanceSection(props) {
	if (!props.people?.length) return null
	const dot = INDICATOR_DOT[props.indicator] || "bg-gray-400"
	const header = h("div", { class: "flex items-center gap-2 mt-2 mb-1" }, [
		h("span", { class: `inline-block h-2 w-2 rounded-full ${dot}` }),
		h("h3", { class: "text-base font-semibold text-gray-900" }, props.title),
		h("span", { class: "text-sm text-gray-500" }, `(${props.people.length})`),
	])
	const list = h(
		"div",
		{ class: "flex flex-col gap-2" },
		props.people.map((p) =>
			h(PersonCard, { person: p, showTimeField: props.showTimeField, showLeaveType: props.showLeaveType, key: p.employee })
		)
	)
	if (!props.collapsible) {
		return h("div", { class: "flex flex-col gap-1" }, [header, list])
	}
	return h("details", { class: "flex flex-col gap-1" }, [h("summary", { class: "cursor-pointer list-none" }, [header]), list])
}
AttendanceSection.props = ["title", "people", "indicator", "showTimeField", "showLeaveType", "collapsible"]

const PersonCard = (props) => {
	const initials =
		(props.person.employee_name || "?")
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((s) => s[0].toUpperCase())
			.join("") || "?"
	const avatar = props.person.image
		? h("img", { src: props.person.image, class: "h-9 w-9 rounded-full object-cover", alt: "" })
		: h("div", { class: "h-9 w-9 rounded-full bg-gray-200 text-gray-600 flex items-center justify-center text-xs font-semibold" }, initials)

	const lines = [
		h("div", { class: "text-sm font-medium text-gray-900 truncate" }, props.person.employee_name || props.person.employee),
		h(
			"div",
			{ class: "text-xs text-gray-500 truncate" },
			[props.person.designation, props.person.department].filter(Boolean).join(" · ") || props.person.company
		),
	]
	if (props.showTimeField && props.person[props.showTimeField]) {
		lines.push(h("div", { class: "text-[11px] text-gray-400" }, fmtTime(props.person[props.showTimeField])))
	}
	if (props.showLeaveType && props.person.leave_type) {
		lines.push(
			h(
				"div",
				{ class: "text-[11px] text-amber-700" },
				props.person.half_day ? `${props.person.leave_type} (half day)` : props.person.leave_type
			)
		)
	}
	if (props.person.status && !props.showTimeField && !props.showLeaveType) {
		lines.push(h("div", { class: "text-[11px] text-gray-500" }, props.person.status))
	}
	return h("div", { class: "flex items-center gap-3 bg-white rounded-xl p-3 border border-gray-100" }, [avatar, h("div", { class: "flex-1 min-w-0" }, lines)])
}
PersonCard.props = ["person", "showTimeField", "showLeaveType"]

function fmtTime(s) {
	if (!s) return ""
	const d = new Date(s.replace(" ", "T"))
	if (isNaN(d.getTime())) return s
	return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

// Layer-2 realtime: catch externally-marked Attendance + bulk leave decisions.
const ROLL_DOCTYPES = ["Employee Checkin", "Leave Application", "Attendance"]
function onAttendanceUpdate(d) {
	if (ROLL_DOCTYPES.includes(d?.doctype)) orgAttendanceToday.reload()
}
onMounted(() => {
	ROLL_DOCTYPES.forEach((dt) => socket.emit("doctype_subscribe", dt))
	socket.on("list_update", onAttendanceUpdate)
})
onBeforeUnmount(() => {
	ROLL_DOCTYPES.forEach((dt) => socket.emit("doctype_unsubscribe", dt))
	socket.off("list_update", onAttendanceUpdate)
})
</script>
