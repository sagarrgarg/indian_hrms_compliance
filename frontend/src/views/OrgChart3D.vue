<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="bg-white border-b border-gray-100">
				<div class="mx-auto w-full max-w-6xl flex items-center justify-between px-4 py-3">
					<div class="flex items-center gap-2">
						<button class="p-1 -ml-1 text-gray-600" @click="$router.push({ name: 'Home' })">
							<FeatherIcon name="arrow-left" class="h-5 w-5" />
						</button>
						<h2 class="text-lg font-bold text-gray-900">{{ __("3D Org Chart") }}</h2>
					</div>
					<span class="text-xs text-gray-500">{{ orgGraph.data?.count || 0 }} {{ __("people") }}</span>
				</div>
			</div>
		</ion-header>

		<ion-content>
			<div class="relative w-full h-full bg-slate-900">
				<div ref="container" class="absolute inset-0"></div>

				<!-- Legend -->
				<div class="absolute top-3 left-3 text-[11px] text-white/80 bg-black/30 rounded-lg p-2 space-y-1">
					<div><span class="inline-block w-2 h-2 rounded-full mr-1" style="background:#10b981"></span>{{ __("On track") }}</div>
					<div><span class="inline-block w-2 h-2 rounded-full mr-1" style="background:#f59e0b"></span>{{ __("Open tasks") }}</div>
					<div><span class="inline-block w-2 h-2 rounded-full mr-1" style="background:#ef4444"></span>{{ __("Overdue") }}</div>
					<div class="pt-1 text-white/50">X {{ __("breadth") }} · Y {{ __("hierarchy") }} · Z {{ __("SOP/KRA/KPI") }}</div>
				</div>

				<!-- Node detail panel -->
				<div
					v-if="selected"
					class="absolute top-3 right-3 w-64 bg-white rounded-xl shadow-lg p-3 text-sm"
				>
					<div class="font-semibold text-gray-900">{{ selected.label }}</div>
					<div class="text-xs text-gray-500">{{ selected.designation || "—" }} · {{ __("Level") }} {{ selected.level }}</div>
					<div class="flex gap-3 mt-2 text-xs">
						<span class="text-amber-600">{{ selected.open_tasks }} {{ __("open") }}</span>
						<span class="text-red-600">{{ selected.overdue_tasks }} {{ __("overdue") }}</span>
					</div>
					<div v-if="selected.kras?.length" class="mt-2">
						<div class="text-[11px] uppercase text-gray-400">{{ __("KRAs") }}</div>
						<div class="text-xs text-gray-700">{{ selected.kras.join(", ") }}</div>
					</div>
					<div v-if="selected.sops?.length" class="mt-2">
						<div class="text-[11px] uppercase text-gray-400">{{ __("SOP / Tasks") }}</div>
						<ul class="text-xs text-gray-700 list-disc ml-4 max-h-32 overflow-auto">
							<li v-for="s in selected.sops" :key="s.name">{{ s.label }} <span class="text-gray-400">({{ s.kind }})</span></li>
						</ul>
					</div>
					<button class="mt-2 text-xs text-indigo-600" @click="selected = null">{{ __("Close") }}</button>
				</div>

				<div v-if="orgGraph.loading" class="absolute inset-0 flex items-center justify-center text-white/70">
					{{ __("Loading…") }}
				</div>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { inject, onMounted, onBeforeUnmount, ref, watch } from "vue"
import { IonPage, IonHeader, IonContent } from "@ionic/vue"
import { FeatherIcon } from "frappe-ui"
import * as THREE from "three"
import { OrbitControls } from "three/addons/controls/OrbitControls.js"

import { orgGraph } from "@/data/orgGraph"

const __ = inject("$translate")
const container = ref(null)
const selected = ref(null)

let scene, camera, renderer, controls, raycaster, pointer, frameId, ro
let pickables = []
const X_GAP = 6, Y_GAP = 7, Z_GAP = 2.2

function nodeColor(n) {
	if (n.overdue_tasks > 0) return 0xef4444
	if (n.open_tasks > 0) return 0xf59e0b
	return 0x10b981
}

function makeLabel(text) {
	const canvas = document.createElement("canvas")
	const ctx = canvas.getContext("2d")
	ctx.font = "28px sans-serif"
	const w = ctx.measureText(text).width + 20
	canvas.width = w
	canvas.height = 40
	ctx.font = "28px sans-serif"
	ctx.fillStyle = "rgba(255,255,255,0.92)"
	ctx.fillText(text, 10, 30)
	const tex = new THREE.CanvasTexture(canvas)
	const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false }))
	sprite.scale.set(w / 26, 40 / 26, 1)
	return sprite
}

function build() {
	const data = orgGraph.data
	if (!scene || !data?.nodes) return

	// clear previous graph (keep lights)
	;[...scene.children].forEach((c) => {
		if (c.userData.graph) scene.remove(c)
	})
	pickables = []

	// X position: spread all nodes at the same level along X
	const byLevel = {}
	data.nodes.forEach((n) => (byLevel[n.level] = byLevel[n.level] || []).push(n))
	const pos = {}
	Object.keys(byLevel).forEach((lvl) => {
		const arr = byLevel[lvl]
		arr.forEach((n, i) => {
			const x = (i - (arr.length - 1) / 2) * X_GAP
			const y = -Number(lvl) * Y_GAP
			pos[n.id] = new THREE.Vector3(x, y, 0)
		})
	})

	const sphereGeo = new THREE.SphereGeometry(0.9, 24, 24)
	const sopGeo = new THREE.BoxGeometry(0.5, 0.5, 0.5)

	data.nodes.forEach((n) => {
		const p = pos[n.id]
		const mesh = new THREE.Mesh(sphereGeo, new THREE.MeshStandardMaterial({ color: nodeColor(n) }))
		mesh.position.copy(p)
		mesh.userData = { graph: true, node: n }
		scene.add(mesh)
		pickables.push(mesh)

		const label = makeLabel(n.label)
		label.position.set(p.x, p.y + 1.4, p.z)
		label.userData.graph = true
		scene.add(label)

		// reports_to edge to parent
		if (n.parent && pos[n.parent]) {
			const g = new THREE.BufferGeometry().setFromPoints([p, pos[n.parent]])
			const line = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0x64748b }))
			line.userData.graph = true
			scene.add(line)
		}

		// Z axis: SOP / KRA / KPI items
		;(n.sops || []).slice(0, 8).forEach((s, j) => {
			const zp = new THREE.Vector3(p.x, p.y, (j + 1) * Z_GAP)
			const col = s.kind === "KPI Metric" ? 0x8b5cf6 : s.kind === "SOP Container" ? 0x06b6d4 : 0x6366f1
			const box = new THREE.Mesh(sopGeo, new THREE.MeshStandardMaterial({ color: col }))
			box.position.copy(zp)
			box.userData = { graph: true, node: n }
			scene.add(box)
			pickables.push(box)
			const g = new THREE.BufferGeometry().setFromPoints([p, zp])
			const line = new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0x334155 }))
			line.userData.graph = true
			scene.add(line)
		})
	})
}

function onClick(event) {
	const rect = renderer.domElement.getBoundingClientRect()
	pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
	pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
	raycaster.setFromCamera(pointer, camera)
	const hits = raycaster.intersectObjects(pickables, false)
	selected.value = hits.length ? hits[0].object.userData.node : null
}

function resize() {
	if (!renderer || !container.value) return
	const w = container.value.clientWidth
	const h = container.value.clientHeight
	renderer.setSize(w, h)
	camera.aspect = w / h
	camera.updateProjectionMatrix()
}

onMounted(() => {
	scene = new THREE.Scene()
	scene.background = new THREE.Color(0x0f172a)
	camera = new THREE.PerspectiveCamera(55, 1, 0.1, 1000)
	camera.position.set(0, 6, 38)
	renderer = new THREE.WebGLRenderer({ antialias: true })
	container.value.appendChild(renderer.domElement)

	scene.add(new THREE.AmbientLight(0xffffff, 0.8))
	const dir = new THREE.DirectionalLight(0xffffff, 0.6)
	dir.position.set(10, 20, 30)
	scene.add(dir)
	scene.add(new THREE.AxesHelper(5))

	controls = new OrbitControls(camera, renderer.domElement)
	controls.enableDamping = true
	raycaster = new THREE.Raycaster()
	pointer = new THREE.Vector2()
	renderer.domElement.addEventListener("click", onClick)

	resize()
	ro = new ResizeObserver(resize)
	ro.observe(container.value)

	const loop = () => {
		frameId = requestAnimationFrame(loop)
		controls.update()
		renderer.render(scene, camera)
	}
	loop()

	if (orgGraph.data) build()
})

watch(() => orgGraph.data, build)

onBeforeUnmount(() => {
	cancelAnimationFrame(frameId)
	ro && ro.disconnect()
	renderer && renderer.domElement.removeEventListener("click", onClick)
	renderer && renderer.dispose()
})
</script>
