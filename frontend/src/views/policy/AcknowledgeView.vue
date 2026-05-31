<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="w-full sm:max-w-3xl sm:mx-auto">
				<div
					class="flex flex-row bg-white shadow-sm py-4 px-3 items-center border-b"
				>
					<Button variant="ghost" class="!px-1 mr-1 hover:bg-white" @click="router.back()">
						<FeatherIcon name="chevron-left" class="h-5 w-5" />
					</Button>
					<h2 class="text-xl font-semibold text-gray-900 truncate">
						{{ __("Policy") }}
					</h2>
				</div>
			</div>
		</ion-header>

		<ion-content class="ion-no-padding">
			<div class="flex flex-col h-full w-full sm:max-w-3xl sm:mx-auto">
				<div v-if="policy" class="flex flex-col gap-5 p-4 pb-28">
					<div class="flex flex-col gap-2">
						<div class="text-xl font-bold text-gray-900">
							{{ policy.policy_name_fetched || policy.policy }}
						</div>
						<div class="flex flex-row items-center gap-2 flex-wrap">
							<ion-badge color="medium">{{ policy.policy_category }}</ion-badge>
							<span class="text-sm text-gray-500">
								{{ __("Version") }} {{ policy.policy_version }}
							</span>
							<ion-badge
								:color="policy.status === 'Acknowledged' ? 'success' : 'warning'"
							>
								{{ policy.status }}
							</ion-badge>
						</div>
						<div
							v-if="policy.status === 'Pending' && policy.due_date"
							class="text-sm text-gray-500"
						>
							{{ __("Due by") }}
							{{ dayjs(policy.due_date).format("D MMM YYYY") }}
						</div>
					</div>

					<div
						v-if="policy.content_html"
						class="prose prose-sm max-w-none text-gray-800 bg-white rounded p-4"
						v-html="policy.content_html"
					/>

					<a
						v-if="policy.attachment"
						:href="policy.attachment"
						target="_blank"
						rel="noopener"
						class="flex flex-row items-center gap-2 text-blue-600 text-sm font-medium"
					>
						<FeatherIcon name="paperclip" class="h-4 w-4" />
						{{ __("Open attached document") }}
					</a>

					<div
						v-if="policy.signed_text"
						class="flex flex-col gap-2 bg-gray-50 rounded p-4 border"
					>
						<div class="text-xs font-medium text-gray-500 uppercase">
							{{ __("Declaration") }}
						</div>
						<div class="text-sm text-gray-700 italic">
							{{ policy.signed_text }}
						</div>
					</div>
				</div>

				<EmptyState v-else :message="__('Policy not found')" />
			</div>
		</ion-content>

		<ion-footer
			v-if="policy && policy.status === 'Pending'"
			class="ion-no-border"
		>
			<div class="w-full sm:max-w-3xl sm:mx-auto bg-white p-4 border-t">
				<Button
					variant="solid"
					class="w-full py-5 text-base"
					:loading="acknowledgePolicy.loading"
					@click="onAcknowledge"
				>
					{{ __("I Acknowledge") }}
				</Button>
			</div>
		</ion-footer>
	</ion-page>
</template>

<script setup>
import { inject, computed } from "vue"
import { useRouter } from "vue-router"
import { IonPage, IonHeader, IonContent, IonFooter, IonBadge } from "@ionic/vue"
import { Button, FeatherIcon, toast } from "frappe-ui"

import EmptyState from "@/components/EmptyState.vue"

import {
	pendingPolicies,
	acknowledgedPolicies,
	acknowledgePolicy,
} from "@/data/policies"

const props = defineProps({
	id: {
		type: String,
		required: true,
	},
})

const __ = inject("$translate")
const dayjs = inject("$dayjs")
const router = useRouter()

const policy = computed(() => {
	const pending = pendingPolicies.data?.find((p) => p.name === props.id)
	if (pending) return pending
	return acknowledgedPolicies.data?.find((p) => p.name === props.id)
})

function onAcknowledge() {
	acknowledgePolicy.submit(
		{ acknowledgement_name: props.id },
		{
			onSuccess() {
				toast({
					title: __("Success"),
					text: __("Policy acknowledged"),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
				pendingPolicies.reload()
				acknowledgedPolicies.reload()
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
