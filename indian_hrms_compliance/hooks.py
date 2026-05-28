app_name = "indian_hrms_compliance"
app_title = "Frappe HR"
app_publisher = "Frappe Technologies Pvt. Ltd."
app_description = "Modern HR and Payroll Software"
app_email = "contact@frappe.io"
app_license = "GNU General Public License (v3)"
required_apps = ["frappe/erpnext"]
source_link = "http://github.com/frappe/indian_hrms_compliance"

add_to_apps_screen = [
	{
		"name": "indian_hrms_compliance",
		"logo": "/assets/indian_hrms_compliance/images/frappe-hr-logo.svg",
		"title": "Frappe HR",
		"route": "/app/hr",
		"has_permission": "indian_hrms_compliance.hr.utils.check_app_permission",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/indian_hrms_compliance/css/indian_hrms_compliance.css"
app_include_js = [
	"indian_hrms_compliance.bundle.js",
]
app_include_css = "indian_hrms_compliance.bundle.css"

# website

# include js, css files in header of web template
# web_include_css = "/assets/indian_hrms_compliance/css/indian_hrms_compliance.css"
# web_include_js = "/assets/indian_hrms_compliance/js/indian_hrms_compliance.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "indian_hrms_compliance/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Employee": "public/js/erpnext/employee.js",
	"Job Offer": "public/js/erpnext/job_offer.js",
	"Company": "public/js/erpnext/company.js",
	"Department": "public/js/erpnext/department.js",
	"Timesheet": "public/js/erpnext/timesheet.js",
	"Payment Entry": "public/js/erpnext/payment_entry.js",
	"Journal Entry": "public/js/erpnext/journal_entry.js",
	"Delivery Trip": "public/js/erpnext/delivery_trip.js",
	"Bank Transaction": "public/js/erpnext/bank_transaction.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

calendars = ["Leave Application"]

# Generators
# ----------

# automatically create page for each record of this doctype
website_generators = ["Job Opening"]

website_route_rules = [
	{"from_route": "/indian_hrms_compliance/<path:app_path>", "to_route": "indian_hrms_compliance"},
	{"from_route": "/hr/<path:app_path>", "to_route": "roster"},
]
# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {
	"methods": [
		"indian_hrms_compliance.utils.get_country",
	],
}

# Installation
# ------------

# before_install = "indian_hrms_compliance.install.before_install"
after_install = "indian_hrms_compliance.install.after_install"
after_migrate = "indian_hrms_compliance.setup.update_select_perm_after_install"

setup_wizard_complete = "indian_hrms_compliance.subscription_utils.update_erpnext_access"

# Uninstallation
# ------------

before_uninstall = "indian_hrms_compliance.uninstall.before_uninstall"
# after_uninstall = "indian_hrms_compliance.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "indian_hrms_compliance.utils.before_app_install"
after_app_install = "indian_hrms_compliance.setup.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

before_app_uninstall = "indian_hrms_compliance.setup.before_app_uninstall"
# after_app_uninstall = "indian_hrms_compliance.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "indian_hrms_compliance.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"Employee Policy Acknowledgement": "indian_hrms_compliance.hr.doctype.employee_policy_acknowledgement.employee_policy_acknowledgement.get_permission_query_conditions",
}

# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

has_upload_permission = {"Employee": "erpnext.setup.doctype.employee.employee.has_upload_permission"}

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Employee": "indian_hrms_compliance.overrides.employee_master.EmployeeMaster",
	"Timesheet": "indian_hrms_compliance.overrides.employee_timesheet.EmployeeTimesheet",
	"Payment Entry": "indian_hrms_compliance.overrides.employee_payment_entry.EmployeePaymentEntry",
	"Project": "indian_hrms_compliance.overrides.employee_project.EmployeeProject",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"User": {
		"validate": [
			"erpnext.setup.doctype.employee.employee.validate_employee_role",
			"indian_hrms_compliance.overrides.employee_master.update_approver_user_roles",
		],
	},
	"Company": {
		"validate": "indian_hrms_compliance.overrides.company.validate_default_accounts",
		"on_update": [
			"indian_hrms_compliance.overrides.company.make_company_fixtures",
			"indian_hrms_compliance.overrides.company.set_default_hr_accounts",
		],
		"on_trash": "indian_hrms_compliance.overrides.company.handle_linked_docs",
	},
	"Holiday List": {
		"on_update": "indian_hrms_compliance.utils.holiday_list.invalidate_cache",
		"on_trash": "indian_hrms_compliance.utils.holiday_list.invalidate_cache",
	},
	"Timesheet": {"validate": "indian_hrms_compliance.hr.utils.validate_active_employee"},
	"Payment Entry": {
		"on_submit": "indian_hrms_compliance.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
		"on_cancel": "indian_hrms_compliance.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
		"on_update_after_submit": "indian_hrms_compliance.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
	},
	"Unreconcile Payment": {
		"on_submit": "indian_hrms_compliance.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
	},
	"Journal Entry": {
		"validate": "indian_hrms_compliance.hr.doctype.expense_claim.expense_claim.validate_expense_claim_in_jv",
		"on_submit": [
			"indian_hrms_compliance.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
			"indian_hrms_compliance.hr.doctype.full_and_final_statement.full_and_final_statement.update_full_and_final_statement_status",
			"indian_hrms_compliance.payroll.doctype.salary_withholding.salary_withholding.update_salary_withholding_payment_status",
		],
		"on_update_after_submit": "indian_hrms_compliance.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
		"on_cancel": [
			"indian_hrms_compliance.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
			"indian_hrms_compliance.payroll.doctype.salary_slip.salary_slip.unlink_ref_doc_from_salary_slip",
			"indian_hrms_compliance.hr.doctype.full_and_final_statement.full_and_final_statement.update_full_and_final_statement_status",
			"indian_hrms_compliance.payroll.doctype.salary_withholding.salary_withholding.update_salary_withholding_payment_status",
		],
	},
	"Loan": {"validate": "indian_hrms_compliance.hr.utils.validate_loan_repay_from_salary"},
	"Employee": {
		"validate": [
			"indian_hrms_compliance.overrides.employee_master.validate_onboarding_process",
			"indian_hrms_compliance.overrides.employee_master.validate_statutory_id_formats",
			"indian_hrms_compliance.overrides.employee_master.validate_person_data_consistency",
			"indian_hrms_compliance.overrides.employee_master.validate_single_primary_employer",
		],
		"on_update": [
			"indian_hrms_compliance.overrides.employee_master.update_approver_role",
			"indian_hrms_compliance.overrides.employee_master.publish_update",
		],
		"after_insert": "indian_hrms_compliance.overrides.employee_master.update_job_applicant_and_offer",
		"on_trash": "indian_hrms_compliance.overrides.employee_master.update_employee_transfer",
		"after_delete": "indian_hrms_compliance.overrides.employee_master.publish_update",
	},
	"Project": {"validate": "indian_hrms_compliance.controllers.employee_boarding_controller.update_employee_boarding_status"},
	"Task": {"on_update": "indian_hrms_compliance.controllers.employee_boarding_controller.update_task"},
	"Job Requisition": {
		"on_update": "indian_hrms_compliance.overrides.job_requisition_workflow.auto_create_opening_on_approval",
	},
	"Job Applicant": {
		"validate": "indian_hrms_compliance.overrides.job_applicant.detect_internal_applicant",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"all": [
		"indian_hrms_compliance.hr.doctype.interview.interview.send_interview_reminder",
	],
	"hourly": [
		"indian_hrms_compliance.hr.doctype.daily_work_summary_group.daily_work_summary_group.trigger_emails",
	],
	"hourly_long": [
		"indian_hrms_compliance.hr.doctype.shift_type.shift_type.update_last_sync_of_checkin",
		"indian_hrms_compliance.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts",
		"indian_hrms_compliance.hr.doctype.shift_schedule_assignment.shift_schedule_assignment.process_auto_shift_creation",
	],
	"daily": [
		"indian_hrms_compliance.controllers.employee_reminders.send_birthday_reminders",
		"indian_hrms_compliance.controllers.employee_reminders.send_work_anniversary_reminders",
		"indian_hrms_compliance.hr.doctype.daily_work_summary_group.daily_work_summary_group.send_summary",
		"indian_hrms_compliance.hr.doctype.interview.interview.send_daily_feedback_reminder",
		"indian_hrms_compliance.hr.doctype.shift_assignment.shift_assignment.mark_expired_shift_assignments_as_inactive",
		"indian_hrms_compliance.hr.doctype.job_opening.job_opening.close_expired_job_openings",
		"indian_hrms_compliance.hr.doctype.probation_review.probation_review.create_probation_review_reminders",
	],
	"daily_long": [
		"indian_hrms_compliance.hr.doctype.leave_ledger_entry.leave_ledger_entry.process_expired_allocation",
		"indian_hrms_compliance.hr.utils.generate_leave_encashment",
		"indian_hrms_compliance.hr.utils.allocate_earned_leaves",
	],
	"weekly": ["indian_hrms_compliance.controllers.employee_reminders.send_reminders_in_advance_weekly"],
	"monthly": ["indian_hrms_compliance.controllers.employee_reminders.send_reminders_in_advance_monthly"],
}

advance_payment_doctypes = ["Leave Encashment", "Gratuity", "Employee Advance"]

invoice_doctypes = ["Expense Claim"]

period_closing_doctypes = ["Payroll Entry"]

accounting_dimension_doctypes = [
	"Expense Claim",
	"Expense Claim Detail",
	"Expense Taxes and Charges",
	"Payroll Entry",
	"Leave Encashment",
]

bank_reconciliation_doctypes = ["Expense Claim"]

# Testing
# -------

before_tests = "indian_hrms_compliance.tests.test_utils.before_tests"

# Overriding Methods
# -----------------------------

# get matching queries for Bank Reconciliation
get_matching_queries = "indian_hrms_compliance.hr.utils.get_matching_queries"

regional_overrides = {
	"India": {
		"indian_hrms_compliance.hr.utils.calculate_annual_eligible_hra_exemption": "indian_hrms_compliance.regional.india.utils.calculate_annual_eligible_hra_exemption",
		"indian_hrms_compliance.hr.utils.calculate_hra_exemption_for_period": "indian_hrms_compliance.regional.india.utils.calculate_hra_exemption_for_period",
		"indian_hrms_compliance.hr.utils.calculate_tax_with_marginal_relief": "indian_hrms_compliance.regional.india.utils.calculate_tax_with_marginal_relief",
	},
}

# ERPNext doctypes for Global Search
global_search_doctypes = {
	"Default": [
		{"doctype": "Salary Slip", "index": 19},
		{"doctype": "Leave Application", "index": 20},
		{"doctype": "Expense Claim", "index": 21},
		{"doctype": "Employee Grade", "index": 37},
		{"doctype": "Job Opening", "index": 39},
		{"doctype": "Job Applicant", "index": 40},
		{"doctype": "Job Offer", "index": 41},
		{"doctype": "Salary Structure Assignment", "index": 42},
		{"doctype": "Appraisal", "index": 43},
	],
}

# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "indian_hrms_compliance.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
override_doctype_dashboards = {
	"Employee": "indian_hrms_compliance.overrides.dashboard_overrides.get_dashboard_for_employee",
	"Holiday List": "indian_hrms_compliance.overrides.dashboard_overrides.get_dashboard_for_holiday_list",
	"Task": "indian_hrms_compliance.overrides.dashboard_overrides.get_dashboard_for_project",
	"Project": "indian_hrms_compliance.overrides.dashboard_overrides.get_dashboard_for_project",
	"Timesheet": "indian_hrms_compliance.overrides.dashboard_overrides.get_dashboard_for_timesheet",
	"Bank Account": "indian_hrms_compliance.overrides.dashboard_overrides.get_dashboard_for_bank_account",
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

ignore_links_on_delete = ["PWA Notification"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"indian_hrms_compliance.auth.validate"
# ]

# Translation
# --------------------------------

# Make link fields search translated document names for these DocTypes
# Recommended only for DocTypes which have limited documents with untranslated names
# For example: Role, Gender, etc.
# translated_search_doctypes = []

company_data_to_be_ignored = [
	"Salary Component Account",
	"Salary Structure",
	"Salary Structure Assignment",
	"Payroll Period",
	"Income Tax Slab",
	"Leave Period",
	"Leave Policy Assignment",
	"Employee Onboarding Template",
	"Employee Separation Template",
]
