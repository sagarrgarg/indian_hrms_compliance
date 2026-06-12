# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document

import indian_hrms_compliance


class PWANotification(Document):
	def on_update(self):
		indian_hrms_compliance.refetch_resource("indian_hrms_compliance:notifications", self.to_user)

	def after_insert(self):
		self.send_push_notification()

	def send_push_notification(self):
		try:
			from frappe.push_notification import PushNotification

			# Project name is what Frappe's push-notification relay
			# (push-notification-relay.frappe.cloud) keys Firebase project + VAPID
			# config under. The relay only knows pre-registered projects;
			# "indian_hrms_compliance" isn't on its allowlist but "hrms" is, and
			# this app is a fork of Frappe HRMS so reusing the official project
			# is appropriate. Switch to a self-hosted relay if you need
			# Firebase isolation.
			push_notification = PushNotification("hrms")
			if push_notification.is_enabled():
				push_notification.send_notification_to_user(
					self.to_user,
					self.reference_document_type,
					self.message,
					link=self.get_notification_link(),
					icon=f"{frappe.utils.get_url()}/assets/indian_hrms_compliance/manifest/favicon-196.png",
				)
		except ImportError:
			# push notifications are not supported in the current framework version
			pass
		except Exception:
			self.log_error(f"Error sending push notification: {self.name}")

	def get_notification_link(self):
		base_url = f"{frappe.utils.get_url()}/indian_hrms_compliance"

		if self.reference_document_type == "Leave Application":
			return f"{base_url}/leave-applications/{self.reference_document_name}"
		elif self.reference_document_type == "Expense Claim":
			return f"{base_url}/expense-claims/{self.reference_document_name}"

		return base_url
