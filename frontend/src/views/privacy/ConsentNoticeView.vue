<template>
	<ion-page>
		<ion-header class="ion-no-border">
			<div class="w-full sm:max-w-3xl sm:mx-auto">
				<div
					class="flex flex-row bg-white shadow-sm py-4 px-3 items-center border-b"
				>
					<Button
						variant="ghost"
						class="!px-1 mr-1 hover:bg-white"
						@click="router.back()"
					>
						<FeatherIcon name="chevron-left" class="h-5 w-5" />
					</Button>
					<h2 class="text-xl font-semibold text-gray-900 truncate">
						{{ __("Consent Notice") }}
					</h2>
				</div>
			</div>
		</ion-header>

		<ion-content class="ion-no-padding">
			<div class="flex flex-col h-full w-full sm:max-w-3xl sm:mx-auto">
				<div v-if="notice" class="flex flex-col gap-5 p-4 pb-32">
					<div class="flex flex-col gap-2">
						<div class="text-xl font-bold text-gray-900">
							{{ notice.purpose_name }}
						</div>
						<div class="flex flex-row items-center gap-2 flex-wrap">
							<ion-badge color="medium">{{ notice.lawful_basis }}</ion-badge>
							<ion-badge :color="statusColor">{{
								__(notice.consent_status)
							}}</ion-badge>
						</div>
					</div>

					<div
						v-if="notice.notice_html || notice.description"
						class="prose prose-sm max-w-none text-gray-800 bg-white rounded p-4"
						v-html="noticeBody"
					/>

					<div class="flex flex-col gap-3 bg-gray-50 rounded p-4 border">
						<div v-if="notice.data_categories" class="flex flex-col gap-1">
							<div class="text-xs font-medium text-gray-500 uppercase">
								{{ __("Data Categories") }}
							</div>
							<div class="text-sm text-gray-700">
								{{ notice.data_categories }}
							</div>
						</div>
						<div
							v-if="notice.retention_period_years"
							class="flex flex-col gap-1"
						>
							<div class="text-xs font-medium text-gray-500 uppercase">
								{{ __("Retention") }}
							</div>
							<div class="text-sm text-gray-700">
								{{ notice.retention_period_years }} {{ __("years") }}
							</div>
						</div>
						<div
							v-if="notice.withdrawal_consequences"
							class="flex flex-col gap-1"
						>
							<div class="text-xs font-medium text-gray-500 uppercase">
								{{ __("If you withdraw") }}
							</div>
							<div class="text-sm text-gray-700">
								{{ notice.withdrawal_consequences }}
							</div>
						</div>
					</div>

					<div
						v-if="isStatutory"
						class="flex flex-row items-start gap-2 bg-amber-50 rounded p-4 border border-amber-200"
					>
						<FeatherIcon
							name="info"
							class="h-4 w-4 text-amber-600 mt-0.5 shrink-0"
						/>
						<div class="text-sm text-amber-800">
							{{
								__(
									"This data is processed under a statutory obligation, not your consent. Your consent is not required and this processing cannot be withdrawn while the legal obligation stands."
								)
							}}
						</div>
					</div>
				</div>

				<EmptyState v-else :message="__('Notice not found')" />
			</div>
		</ion-content>

		<ion-footer v-if="notice && !isStatutory" class="ion-no-border">
			<div class="w-full sm:max-w-3xl sm:mx-auto bg-white p-4 border-t">
				<Button
					v-if="notice.consent_status !== 'Active'"
					variant="solid"
					class="w-full py-5 text-base"
					:loading="grantConsent.loading"
					@click="onGrant"
				>
					{{ __("I Grant Consent") }}
				</Button>
				<Button
					v-else
					variant="subtle"
					theme="red"
					class="w-full py-5 text-base"
					:loading="withdrawConsent.loading"
					@click="onWithdraw"
				>
					{{ __("Withdraw Consent") }}
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
import { renderMarkdown } from "@/utils/markdown"

import {
	consentNotice,
	grantConsent,
	withdrawConsent,
	consentOverview,
} from "@/data/privacy"

const props = defineProps({
	purposeCode: {
		type: String,
		required: true,
	},
})

const __ = inject("$translate")
const router = useRouter()

consentNotice.fetch({ purpose_code: props.purposeCode })

const notice = computed(() => consentNotice.data)

const isStatutory = computed(
	() => notice.value?.lawful_basis === "Statutory Obligation"
)

const noticeBody = computed(() =>
	renderMarkdown(notice.value?.notice_html || notice.value?.description || "")
)

const statusColor = computed(() => {
	switch (notice.value?.consent_status) {
		case "Active":
			return "success"
		case "Withdrawn":
			return "medium"
		default:
			return "warning"
	}
})

function refreshAndBack() {
	consentNotice.fetch({ purpose_code: props.purposeCode })
	consentOverview.reload()
	router.back()
}

function onGrant() {
	grantConsent.submit(
		{ purpose_code: props.purposeCode },
		{
			onSuccess() {
				toast({
					title: __("Success"),
					text: __("Consent granted"),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
				refreshAndBack()
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

function onWithdraw() {
	withdrawConsent.submit(
		{ purpose_code: props.purposeCode },
		{
			onSuccess() {
				toast({
					title: __("Success"),
					text: __("Consent withdrawn"),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
				refreshAndBack()
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
