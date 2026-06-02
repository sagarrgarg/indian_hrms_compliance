<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="w-full sm:max-w-3xl sm:mx-auto">
				<div class="flex flex-row bg-white shadow-sm py-4 px-3 items-center border-b">
					<Button variant="ghost" class="!px-1 mr-1 hover:bg-white" @click="router.back()">
						<FeatherIcon name="chevron-left" class="h-5 w-5" />
					</Button>
					<h2 class="text-xl font-semibold text-gray-900 truncate">{{ __("Assign Task to Team") }}</h2>
				</div>
			</div>
		</ion-header>

		<ion-content>
			<div class="w-full sm:max-w-3xl sm:mx-auto p-4 flex flex-col gap-5 pb-28">
				<FormControl
					type="select"
					:label="__('Team Member')"
					:options="memberOptions"
					v-model="form.employee"
				/>
				<FormControl type="text" :label="__('Task Title')" v-model="form.title" :placeholder="__('What needs to be done')" />
				<FormControl type="date" :label="__('Due Date')" v-model="form.due_date" />
				<FormControl type="textarea" :label="__('Details (optional)')" v-model="form.description" />

				<p v-if="!myTeam.data?.length" class="text-sm text-amber-600">
					{{ __("You have no direct reports to assign tasks to.") }}
				</p>

				<Button
					variant="solid"
					class="w-full py-5 text-base"
					:loading="createTeamTask.loading"
					:disabled="!isValid"
					@click="onAssign"
				>
					{{ __("Assign Task") }}
				</Button>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { computed, inject, reactive } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonHeader, IonContent } from "@ionic/vue"
import { Button, FormControl, FeatherIcon, toast } from "frappe-ui"

import { myTeam, createTeamTask, myTasks } from "@/data/tasks"

const __ = inject("$translate")
const router = useRouter()

myTeam.fetch()

const memberOptions = computed(() => [
	{ label: __("Select a team member"), value: "" },
	...(myTeam.data || []).map((m) => ({ label: `${m.employee_name} (${m.designation || m.name})`, value: m.name })),
])

const form = reactive({ employee: "", title: "", due_date: "", description: "" })

const isValid = computed(() => !!form.employee && !!form.title.trim())

function onAssign() {
	createTeamTask.submit(
		{
			employee: form.employee,
			title: form.title.trim(),
			due_date: form.due_date || undefined,
			description: form.description || undefined,
		},
		{
			onSuccess() {
				toast({
					title: __("Assigned"),
					text: __("Task assigned to your team member"),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
				myTasks.reload()
				router.back()
			},
			onError(error) {
				toast({
					title: __("Error"),
					text: __(error?.messages?.[0] || error.message),
					icon: "alert-circle",
					position: "bottom-center",
					iconClasses: "text-red-500",
				})
			},
		}
	)
}
</script>
