<template>
	<svg :viewBox="`0 0 ${width} ${height}`" class="w-full h-12" preserveAspectRatio="none">
		<polyline
			v-if="points.length > 1"
			:points="linePoints"
			fill="none"
			:stroke="color"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<polygon v-if="points.length > 1" :points="areaPoints" :fill="color" fill-opacity="0.12" />
		<circle v-if="points.length" :cx="lastX" :cy="lastY" r="2.5" :fill="color" />
	</svg>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	points: { type: Array, default: () => [] },
	color: { type: String, default: "#6366f1" },
})

const width = 100
const height = 32
const pad = 3

const coords = computed(() => {
	const pts = props.points.map(Number)
	const max = Math.max(...pts, 1)
	const min = Math.min(...pts, 0)
	const span = max - min || 1
	const stepX = pts.length > 1 ? (width - pad * 2) / (pts.length - 1) : 0
	return pts.map((v, i) => {
		const x = pad + i * stepX
		const y = height - pad - ((v - min) / span) * (height - pad * 2)
		return [x, y]
	})
})

const linePoints = computed(() => coords.value.map((c) => c.join(",")).join(" "))
const areaPoints = computed(() => {
	const c = coords.value
	if (!c.length) return ""
	return `${pad},${height - pad} ${linePoints.value} ${c[c.length - 1][0]},${height - pad}`
})
const lastX = computed(() => (coords.value.length ? coords.value[coords.value.length - 1][0] : 0))
const lastY = computed(() => (coords.value.length ? coords.value[coords.value.length - 1][1] : 0))
</script>
