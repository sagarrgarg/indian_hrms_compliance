import frappe


def get_context(context):
	# Prefill the hidden invite token from the URL (?invite_token=...) so an
	# invited candidate's submission is flagged. Plain public visits skip this.
	token = frappe.form_dict.get("invite_token")
	if token:
		context.invite_token = token
