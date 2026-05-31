<template>
	<div class="flex flex-col gap-3 my-2 w-full">
		<div class="text-base font-semibold text-gray-900 px-1">{{ title || __("Quick Links") }}</div>
		<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
			<router-link
				v-for="link in props.items"
				:key="link.title"
				:to="{ name: link.route }"
				:class="[
					'group flex flex-col gap-2 rounded-2xl p-3.5 border shadow-sm transition active:scale-95 hover:shadow-md',
					tone(link.color).card,
				]"
			>
				<span
					:class="[
						'flex items-center justify-center h-10 w-10 rounded-xl',
						tone(link.color).chip,
					]"
				>
					<component :is="link.icon" class="h-5 w-5" />
				</span>
				<span class="text-sm font-medium text-gray-800 leading-tight">{{ link.title }}</span>
			</router-link>
		</div>
	</div>
</template>

<script setup>
const props = defineProps({
	title: { type: String, required: false, default: "" },
	items: { type: Array, required: true },
})

// Full class strings (not concatenated) so Tailwind JIT keeps them.
const TONES = {
	indigo: { card: "bg-indigo-50 border-indigo-100", chip: "bg-indigo-100 text-indigo-600" },
	sky: { card: "bg-sky-50 border-sky-100", chip: "bg-sky-100 text-sky-600" },
	violet: { card: "bg-violet-50 border-violet-100", chip: "bg-violet-100 text-violet-600" },
	emerald: { card: "bg-emerald-50 border-emerald-100", chip: "bg-emerald-100 text-emerald-600" },
	amber: { card: "bg-amber-50 border-amber-100", chip: "bg-amber-100 text-amber-600" },
	orange: { card: "bg-orange-50 border-orange-100", chip: "bg-orange-100 text-orange-600" },
	teal: { card: "bg-teal-50 border-teal-100", chip: "bg-teal-100 text-teal-600" },
	blue: { card: "bg-blue-50 border-blue-100", chip: "bg-blue-100 text-blue-600" },
	fuchsia: { card: "bg-fuchsia-50 border-fuchsia-100", chip: "bg-fuchsia-100 text-fuchsia-600" },
	rose: { card: "bg-rose-50 border-rose-100", chip: "bg-rose-100 text-rose-600" },
	cyan: { card: "bg-cyan-50 border-cyan-100", chip: "bg-cyan-100 text-cyan-600" },
	lime: { card: "bg-lime-50 border-lime-100", chip: "bg-lime-100 text-lime-600" },
	purple: { card: "bg-purple-50 border-purple-100", chip: "bg-purple-100 text-purple-600" },
	pink: { card: "bg-pink-50 border-pink-100", chip: "bg-pink-100 text-pink-600" },
}

function tone(color) {
	return TONES[color] || TONES.indigo
}
</script>
