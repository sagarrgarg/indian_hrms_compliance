<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="w-full sm:max-w-3xl sm:mx-auto">
				<div class="flex flex-col bg-white shadow-sm p-4">
					<div class="flex flex-row justify-between items-center">
						<div class="flex flex-row items-center gap-2">
							<button
								v-if="props.back"
								class="p-1 -ml-1 text-gray-700 active:scale-90 transition"
								:aria-label="__('Back')"
								@click="goBack"
							>
								<FeatherIcon name="arrow-left" class="h-5 w-5" />
							</button>
							<h2 class="text-xl font-bold text-gray-900">
								{{ props.pageTitle || __("Frappe HR") }}
							</h2>
							<EmployeeSwitcher />
						</div>
						<div class="flex flex-row items-center gap-3 ml-auto">
							<router-link
								:to="{ name: 'Notifications' }"
								v-slot="{ navigate }"
								class="flex flex-col items-center"
							>
								<span class="relative inline-block" @click="navigate">
									<FeatherIcon name="bell" class="h-6 w-6" />
									<span
										v-if="unreadNotificationsCount.data"
										class="absolute top-0 right-0.5 inline-block w-2 h-2 bg-red-600 rounded-full border border-white"
									>
									</span>
								</span>
							</router-link>
							<router-link
								:to="{ name: 'Profile' }"
								class="flex flex-col items-center"
							>
								<Avatar
									:image="user.data.user_image"
									:label="user.data.first_name"
									size="xl"
								/>
							</router-link>
						</div>
					</div>
				</div>
			</div>
		</ion-header>

		<ion-content class="ion-no-padding">
			<div class="flex flex-col h-screen w-full sm:max-w-3xl sm:mx-auto">
				<slot name="body"></slot>
			</div>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { IonHeader, IonContent, IonPage } from "@ionic/vue"
import { FeatherIcon, Avatar } from "frappe-ui"
import { useRouter } from "vue-router"

import EmployeeSwitcher from "@/components/EmployeeSwitcher.vue"
import { unreadNotificationsCount } from "@/data/notifications"

import { inject } from "vue"

const user = inject("$user")
const __ = inject("$translate")
const router = useRouter()

const props = defineProps({
	pageTitle: {
		type: String,
		required: false,
		default: "",
	},
	// Show a back chevron — set on pushed sub-pages (not on bottom-tab roots).
	back: {
		type: Boolean,
		default: false,
	},
})

function goBack() {
	if (window.history.length > 1) router.back()
	else router.push({ name: "Home" })
}
</script>
