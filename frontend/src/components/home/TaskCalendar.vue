<template>
	<div class="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
		<div class="flex items-center justify-between mb-3">
			<h3 class="text-sm font-semibold text-gray-800">{{ monthLabel }}</h3>
			<div class="flex items-center gap-1">
				<button class="p-1 text-gray-500 hover:text-gray-800" @click="offset--">
					<FeatherIcon name="chevron-left" class="h-4 w-4" />
				</button>
				<button class="p-1 text-gray-500 hover:text-gray-800" @click="offset = 0" :title="__('Today')">
					<FeatherIcon name="calendar" class="h-4 w-4" />
				</button>
				<button class="p-1 text-gray-500 hover:text-gray-800" @click="offset++">
					<FeatherIcon name="chevron-right" class="h-4 w-4" />
				</button>
			</div>
		</div>

		<div class="grid grid-cols-7 gap-1 text-center">
			<div v-for="d in weekdays" :key="d" class="text-[10px] font-medium text-gray-400 py-1">{{ d }}</div>
			<div
				v-for="(cell, i) in cells"
				:key="i"
				:class="[
					'aspect-square flex flex-col items-center justify-center rounded-lg text-xs',
					cell ? 'text-gray-700' : '',
					cell && cell.isToday ? 'bg-indigo-600 text-white font-bold' : '',
					cell && !cell.isToday && cell.due ? 'bg-gray-50' : '',
				]"
			>
				<template v-if="cell">
					<span>{{ cell.day }}</span>
					<span
						v-if="cell.due"
						:class="[
							'mt-0.5 h-1.5 w-1.5 rounded-full',
							cell.isToday ? 'bg-white' : cell.overdue ? 'bg-red-500' : 'bg-indigo-500',
						]"
					/>
				</template>
			</div>
		</div>

		<div class="flex items-center gap-4 mt-3 text-[10px] text-gray-400">
			<span class="flex items-center gap-1"><span class="h-1.5 w-1.5 rounded-full bg-indigo-500" /> {{ __("Upcoming") }}</span>
			<span class="flex items-center gap-1"><span class="h-1.5 w-1.5 rounded-full bg-red-500" /> {{ __("Overdue") }}</span>
		</div>
	</div>
</template>

<script setup>
import { computed, inject, ref } from "vue"
import { FeatherIcon } from "frappe-ui"

const __ = inject("$translate")
const props = defineProps({ tasks: { type: Array, default: () => [] } })

const weekdays = ["S", "M", "T", "W", "T", "F", "S"]
const offset = ref(0)
const now = new Date()

const viewDate = computed(() => new Date(now.getFullYear(), now.getMonth() + offset.value, 1))
const monthLabel = computed(() =>
	viewDate.value.toLocaleString("default", { month: "long", year: "numeric" }),
)

const todayStr = computed(() => new Date().toISOString().slice(0, 10))

// date string -> { count, overdue }
const dueMap = computed(() => {
	const map = {}
	for (const t of props.tasks || []) {
		if (!t.due_date) continue
		const key = String(t.due_date).slice(0, 10)
		const done = ["Completed", "Archived", "Closed"].includes(t.status)
		if (done) continue
		if (!map[key]) map[key] = { count: 0, overdue: false }
		map[key].count++
		if (key < todayStr.value) map[key].overdue = true
	}
	return map
})

const cells = computed(() => {
	const y = viewDate.value.getFullYear()
	const m = viewDate.value.getMonth()
	const firstWeekday = new Date(y, m, 1).getDay()
	const daysInMonth = new Date(y, m + 1, 0).getDate()
	const out = []
	for (let i = 0; i < firstWeekday; i++) out.push(null)
	for (let day = 1; day <= daysInMonth; day++) {
		const key = `${y}-${String(m + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`
		const due = dueMap.value[key]
		out.push({ day, isToday: key === todayStr.value, due: !!due, overdue: due?.overdue })
	}
	return out
})
</script>
