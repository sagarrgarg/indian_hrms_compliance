import { createResource, createListResource } from "frappe-ui"
import { userResource } from "./user"

export const unreadNotificationsCount = createResource({
	url: "indian_hrms_compliance.api.get_unread_notifications_count",
	cache: "indian_hrms_compliance:unread_notifications_count",
	initialData: 0,
	auto: true,
})

export const notifications = createListResource({
	doctype: "PWA Notification",
	filters: { to_user: userResource.data.name },
	fields: [
		"name",
		"from_user",
		"message",
		"read",
		"creation",
		"reference_document_type",
		"reference_document_name",
	],
	auto: false,
	cache: "indian_hrms_compliance:notifications",
	orderBy: "creation desc",
	onSuccess() {
		unreadNotificationsCount.reload()
	},
})

export const arePushNotificationsEnabled = createResource({
	url: "indian_hrms_compliance.api.are_push_notifications_enabled",
	cache: "indian_hrms_compliance:push_notifications_enabled",
	auto: true,
})
