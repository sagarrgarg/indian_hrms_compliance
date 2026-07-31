import os

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.desk.page.setup_wizard.install_fixtures import (
	_,  # NOTE: this is not the real translation function
)
from frappe.desk.page.setup_wizard.setup_wizard import make_records

from indian_hrms_compliance.overrides.company import delete_company_fixtures


def after_install():
	sync_custom_fields()
	apply_property_setters()
	make_fixtures()
	setup_notifications()
	update_hr_defaults()
	add_non_standard_user_types()
	set_single_defaults()
	create_default_role_profiles()
	run_post_install_patches()


def before_uninstall():
	delete_custom_fields(get_custom_fields())
	delete_custom_fields(get_salary_slip_loan_fields())
	delete_company_fixtures()


def after_app_install(app_name):
	"""Set up loan integration with payroll"""
	if app_name != "lending":
		return

	print("Updating payroll setup for loans")
	create_custom_fields(get_salary_slip_loan_fields(), ignore_validate=True)
	add_lending_docperms_to_ess()


def before_app_uninstall(app_name):
	"""Clean up loan integration with payroll"""
	if app_name != "lending":
		return

	print("Updating payroll setup for loans")
	delete_custom_fields(get_salary_slip_loan_fields())
	remove_lending_docperms_from_ess()


def sync_custom_fields():
	"""Idempotently (re)create all HR/Payroll custom fields.

	Runs on after_install AND after_migrate so field definitions in
	get_custom_fields() are the single source of truth and self-heal: a site
	installed before a field was added picks it up on the next migrate, instead
	of silently drifting (the cause of past 'Company has no attribute
	default_payroll_payable_account' failures). create_custom_fields upserts, so
	this is safe to re-run."""
	create_custom_fields(get_custom_fields(), ignore_validate=True)
	create_salary_slip_loan_fields()
	remove_deprecated_custom_fields()


def seed_governance_profile():
	"""after_migrate: give existing companies a Governance Profile from their size.

	A Custom Field default only applies to NEW companies; existing ones read NULL
	→ Startup, which silently empties the KPI scorecard (a Growth+ surface). Seed
	from headcount so the change is deliberate. Blank-only + idempotent, and an
	after_migrate hook (NOT a patch) because the field is created in after_migrate
	— a patch would run too early and no-op forever."""
	try:
		if not frappe.get_meta("Company").has_field("governance_profile"):
			return
		from indian_hrms_compliance.api.governance import suggest_profile

		for company in frappe.get_all("Company", pluck="name"):
			if frappe.db.get_value("Company", company, "governance_profile"):
				continue
			frappe.db.set_value(
				"Company", company, "governance_profile", suggest_profile(company), update_modified=False
			)
	except Exception:
		frappe.db.rollback()
		frappe.log_error("governance_profile seed failed")


def backfill_reports_to_from_heads():
	"""after_migrate: fill empty reports_to from the department tree.

	Runs here, NOT as a patch: the department_head Custom Field is created by
	sync_custom_fields (also after_migrate), so a patch — which runs BEFORE
	after_migrate — would find no field and become a permanent no-op. Blank-only
	and idempotent, so running every migrate just converges as HR sets heads."""
	try:
		from indian_hrms_compliance.overrides.org_tree import backfill_reports_to

		backfill_reports_to()
	except Exception:
		frappe.db.rollback()
		frappe.log_error("reports_to backfill failed")


def reconcile_hrms_task_risk_tiers():
	"""after_migrate: fill blank HRMS Task risk tiers (idempotent, blank-only).

	Lives here as well as in its patch so a site that never ran the patch — a
	restored dump, a skipped migrate — still converges. Because it only ever
	touches BLANK tiers it can run on every migrate without overriding a tier
	someone deliberately set."""
	try:
		from indian_hrms_compliance.hr.doctype.hrms_task.hrms_task import reconcile_risk_tiers

		repaired = reconcile_risk_tiers()
		if repaired:
			print(f"  Derived risk_tier for {repaired} HRMS Task(s)")
	except Exception:
		# Never let a cosmetic backfill abort a migrate. Roll back BEFORE logging:
		# on Postgres a failed statement poisons the transaction, so the Error Log
		# insert would itself raise and defeat the point. (Matches the patch twin.)
		frappe.db.rollback()
		frappe.log_error("HRMS Task risk tier reconciliation failed")


def reconcile_attendance_request_status():
	"""Self-heal Attendance Request `status` from docstatus on every migrate.

	The one-shot patches (backfill_attendance_request_status +
	fix_attendance_request_status_from_docstatus) only run when the Patch Log
	says they haven't — a restored dump or skipped migrate leaves submitted
	rows reading 'Open' (or blank, which the Desk list then shows as 'Draft').
	Running the same idempotent reconciliation on after_migrate makes every
	site converge regardless of patch-log state.

	Never overwrites a *decided* draft — Rejected / Needs Clarification are
	docstatus 0 with a non-blank status and are left untouched."""
	if not frappe.db.table_exists("Attendance Request"):
		return
	if not frappe.get_meta("Attendance Request").has_field("status"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabAttendance Request`
		SET status = CASE docstatus
			WHEN 1 THEN 'Approved'
			WHEN 2 THEN 'Cancelled'
			ELSE 'Open'
		END
		WHERE
			(docstatus IN (1, 2) AND (status IS NULL OR status IN ('', 'Open')))
			OR (docstatus = 0 AND (status IS NULL OR status = ''))
		"""
	)


def seed_grievance_types():
	"""Self-heal the Grievance Type master.

	Runs on after_migrate. Seeds the standard types ONLY when the table is
	empty — a fresh or drifted site whose grievance form would otherwise show
	an empty type dropdown. A site that has curated its own type list (even one
	custom type) is left untouched, so this never resurrects a deliberately
	deleted type. Idempotent."""
	if not frappe.db.table_exists("Grievance Type"):
		return
	if frappe.db.count("Grievance Type"):
		return

	from indian_hrms_compliance.patches.v15_0.enhance_employee_grievance import (
		GRIEVANCE_TYPE_SEEDS,
	)

	has_defaults = frappe.get_meta("Grievance Type").has_field("default_severity")
	for spec in GRIEVANCE_TYPE_SEEDS:
		values = {
			"doctype": "Grievance Type",
			"name": spec["name"],
			"description": spec["description"],
		}
		if has_defaults:
			values["default_severity"] = spec["default_severity"]
			values["default_sla_days"] = spec["default_sla_days"]
		frappe.get_doc(values).insert(ignore_permissions=True)
	print(f"  Seeded {len(GRIEVANCE_TYPE_SEEDS)} Grievance Types (was empty)")


def remove_deprecated_custom_fields():
	"""Delete custom fields that were removed from the app (idempotent).

	Company.default_leave_period is derived from the Fiscal Year now, so the
	stored field is dropped to avoid a redundant, drift-prone second source."""
	for name in ("Company-default_leave_period",):
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True)


def apply_property_setters():
	"""Idempotently override properties on upstream (ERPNext) doctype fields.

	Runs on after_install AND after_migrate (see hooks.py) so the overrides are a
	single source of truth and self-heal, mirroring sync_custom_fields().
	make_property_setter upserts, so this is safe to re-run."""
	# Employee.salary_mode: default to Bank and never leave it blank. A missing
	# salary mode silently breaks bank-transfer payout files and statutory exports.
	make_property_setter(
		"Employee", "salary_mode", "default", "Bank", "Data", validate_fields_for_doctype=False
	)
	make_property_setter(
		"Employee", "salary_mode", "reqd", 1, "Check", validate_fields_for_doctype=False
	)

	# Hide Employee.ctc + salary_currency: redundant at intake — the authoritative pay
	# figure lives on Salary Structure Assignment, and Salary Slip computes its own ctc
	# from the structure, so Employee.ctc feeds no payroll. (Employee Promotion still
	# writes ctc and the PWA Profile still reads it via API; hiding the form field
	# touches neither.)
	make_property_setter(
		"Employee", "ctc", "hidden", 1, "Check", validate_fields_for_doctype=False
	)
	make_property_setter(
		"Employee", "salary_currency", "hidden", 1, "Check", validate_fields_for_doctype=False
	)


def get_custom_fields():
	"""HR specific custom fields that need to be added to the masters in ERPNext"""
	return {
		"Company": [
			{
				"fieldname": "hr_and_payroll_tab",
				"fieldtype": "Tab Break",
				"label": _("HR & Payroll"),
				"insert_after": "credit_limit",
			},
			{
				"fieldname": "hr_settings_section",
				"fieldtype": "Section Break",
				"label": _("HR & Payroll Settings"),
				"insert_after": "hr_and_payroll_tab",
			},
			{
				"fieldname": "governance_profile",
				"fieldtype": "Select",
				"label": _("Governance Profile"),
				"options": "Startup\nGrowth\nRegulated",
				"default": "Startup",
				"insert_after": "hr_settings_section",
				"description": _(
					"Dial 2: how much of the governance spine this company uses. Startup = lean "
					"(tasks + tiers only). Growth = + playbooks, KPI scorecards, Standard-tier "
					"default. Regulated = + the Control Register (auto-RCM) and evidence export. "
					"Statutory / money-movement tasks are born Critical in EVERY profile."
				),
			},
			{
				"depends_on": "eval:!doc.__islocal",
				"fieldname": "default_expense_claim_payable_account",
				"fieldtype": "Link",
				"ignore_user_permissions": 1,
				"label": _("Default Expense Claim Payable Account"),
				"no_copy": 1,
				"options": "Account",
				"insert_after": "hr_settings_section",
			},
			{
				"fieldname": "default_employee_advance_account",
				"fieldtype": "Link",
				"label": _("Default Employee Advance Account"),
				"no_copy": 1,
				"options": "Account",
				"insert_after": "default_expense_claim_payable_account",
			},
			{
				"fieldname": "column_break_10",
				"fieldtype": "Column Break",
				"insert_after": "default_employee_advance_account",
			},
			{
				"depends_on": "eval:!doc.__islocal",
				"fieldname": "default_payroll_payable_account",
				"fieldtype": "Link",
				"ignore_user_permissions": 1,
				"label": _("Default Payroll Payable Account"),
				"no_copy": 1,
				"options": "Account",
				"insert_after": "column_break_10",
			},
			{
				"fieldname": "salary_components_tab",
				"fieldtype": "Tab Break",
				"label": _("Salary Components"),
				"insert_after": "registration_details_for_printing",
			},
			{
				"fieldname": "employee_onboarding_defaults_section",
				"fieldtype": "Section Break",
				"label": _("Employee Onboarding Defaults"),
				"description": _(
					"Defaults applied when a new employee of this company is activated. "
					"The Leave Policy is auto-assigned if enabled in HR Settings."
				),
				"insert_after": "default_payroll_payable_account",
			},
			{
				"fieldname": "default_leave_policy",
				"fieldtype": "Link",
				"label": _("Default Leave Policy"),
				"options": "Leave Policy",
				"insert_after": "employee_onboarding_defaults_section",
			},
			# Default Leave Period is intentionally NOT a company field: the leave
			# period is derived from the Fiscal Year (India), so storing it per
			# company would be a redundant second source. See leave_period_setup.
			{
				"fieldname": "employee_onboarding_defaults_column",
				"fieldtype": "Column Break",
				"insert_after": "default_leave_policy",
			},
			{
				"fieldname": "default_shift_type",
				"fieldtype": "Link",
				"label": _("Default Shift"),
				"options": "Shift Type",
				"insert_after": "employee_onboarding_defaults_column",
			},
			{
				"fieldname": "default_salary_structure",
				"fieldtype": "Link",
				"label": _("Default Salary Structure"),
				"options": "Salary Structure",
				"insert_after": "default_shift_type",
			},
			{
				"fieldname": "statutory_registration_section",
				"fieldtype": "Section Break",
				"label": _("Statutory Registration"),
				"description": _(
					"Establishment codes printed on the Wage Register and statutory returns."
				),
				"insert_after": "default_salary_structure",
			},
			{
				"fieldname": "pf_establishment_code",
				"fieldtype": "Data",
				"label": _("PF Establishment Code"),
				"description": _("Firm PF Number, e.g. DL/CPM/10709"),
				"insert_after": "statutory_registration_section",
			},
			{
				"fieldname": "esic_establishment_code",
				"fieldtype": "Data",
				"label": _("ESIC Establishment Code"),
				"description": _("Firm ESIC Number (17 digits)"),
				"insert_after": "pf_establishment_code",
			},
			{
				"fieldname": "statutory_registration_column",
				"fieldtype": "Column Break",
				"insert_after": "esic_establishment_code",
			},
			{
				"fieldname": "lwf_establishment_code",
				"fieldtype": "Data",
				"label": _("LWF Registration Number"),
				"insert_after": "statutory_registration_column",
			},
		],
		"Department": [
			{
				"fieldname": "org_head_section",
				"fieldtype": "Section Break",
				"label": _("Headship"),
				"insert_after": "disabled",
			},
			{
				"fieldname": "department_head",
				"fieldtype": "Link",
				"label": _("Department Head"),
				"options": "Employee",
				"insert_after": "org_head_section",
				"description": _(
					"The one person who heads this department. Seeds the reporting tree — "
					"members with no manager derive their reports_to from here — and is the "
					"default target for 'assign to head' and escalations."
				),
			},
			{
				"fieldname": "acting_head",
				"fieldtype": "Link",
				"label": _("Acting Head"),
				"options": "Employee",
				"insert_after": "department_head",
				"description": _("Effective-dated cover while the head is on leave or the seat is interim-vacant."),
			},
			{
				"fieldname": "acting_until",
				"fieldtype": "Date",
				"label": _("Acting Until"),
				"depends_on": "acting_head",
				"insert_after": "acting_head",
				"description": _("Last date the Acting Head covers. After this it reverts to the Department Head."),
			},
			{
				"fieldname": "org_head_col_break",
				"fieldtype": "Column Break",
				"insert_after": "acting_until",
			},
			{
				"fieldname": "default_kras",
				"fieldtype": "Table",
				"label": _("Default KRAs (Growth+)"),
				"options": "Department Default KRA",
				"insert_after": "org_head_col_break",
				"description": _(
					"A new joiner in this department is suggested these KRAs' applicable tasks. "
					"A convenience for Growth+ companies; Startup profiles can ignore it."
				),
			},
			{
				"fieldname": "section_break_4",
				"fieldtype": "Section Break",
				"insert_after": "default_kras",
			},
			{
				"fieldname": "payroll_cost_center",
				"fieldtype": "Link",
				"label": _("Payroll Cost Center"),
				"options": "Cost Center",
				"insert_after": "section_break_4",
			},
			{
				"fieldname": "column_break_9",
				"fieldtype": "Column Break",
				"insert_after": "payroll_cost_center",
			},
			{
				"description": _("Days for which Holidays are blocked for this department."),
				"fieldname": "leave_block_list",
				"fieldtype": "Link",
				"in_list_view": 1,
				"label": _("Leave Block List"),
				"options": "Leave Block List",
				"insert_after": "column_break_9",
			},
			{
				"description": _("The first Approver in the list will be set as the default Approver."),
				"fieldname": "approvers",
				"fieldtype": "Section Break",
				"label": _("Approvers"),
				"insert_after": "leave_block_list",
			},
			{
				"fieldname": "shift_request_approver",
				"fieldtype": "Table",
				"label": _("Shift Request Approver"),
				"options": "Department Approver",
				"insert_after": "approvers",
			},
			{
				"fieldname": "leave_approvers",
				"fieldtype": "Table",
				"label": _("Leave Approver"),
				"options": "Department Approver",
				"insert_after": "shift_request_approver",
			},
			{
				"fieldname": "expense_approvers",
				"fieldtype": "Table",
				"label": _("Expense Approver"),
				"options": "Department Approver",
				"insert_after": "leave_approvers",
			},
		],
		"Designation": [
			{
				"fieldname": "seniority_rank",
				"fieldtype": "Int",
				"label": _("Seniority Rank"),
				"insert_after": "description",
				"non_negative": 1,
				"description": _(
					"Optional ordering hint (higher = more senior): org-chart display order and "
					"the tie-break for 'most senior active person' when a head and acting head are "
					"both vacant. Not a designation ladder — just a single ordering number."
				),
			},
			{
				"fieldname": "appraisal_template",
				"fieldtype": "Link",
				"label": _("Appraisal Template"),
				"options": "Appraisal Template",
				"insert_after": "seniority_rank",
				"allow_in_quick_entry": 1,
			},
			{
				"fieldname": "required_skills_section",
				"fieldtype": "Section Break",
				"label": _("Required Skills"),
				"insert_after": "appraisal_template",
			},
			{
				"fieldname": "skills",
				"fieldtype": "Table",
				"label": _("Skills"),
				"options": "Designation Skill",
				"insert_after": "required_skills_section",
			},
			{
				"fieldname": "department",
				"fieldtype": "Link",
				"label": _("Department"),
				"options": "Department",
				"insert_after": "skills",
				"description": _(
					"Scope this title to a department (optional). When set, the designation is "
					"only selectable for employees of that department, and its people's head is "
					"unambiguously that department's head. Leave empty for cross-department "
					"titles like 'Driver' or 'Office Assistant'."
				),
			},
		],
		"Employee": [
			{
				"fieldname": "default_task_delegate",
				"fieldtype": "Link",
				"label": _("Default Task Delegate"),
				"options": "Employee",
				"insert_after": "reports_to",
				"description": _(
					"Where open task instances go for leave cover (a peer / deputy). Falls back "
					"to the reporting manager when empty."
				),
			},
			{
				"fieldname": "leave_policy",
				"fieldtype": "Link",
				"label": _("Leave Policy"),
				"options": "Leave Policy",
				"insert_after": "holiday_list",
				"description": _(
					"Overrides the company's default Leave Policy for this employee. Leave blank to use the company default."
				),
			},
			{
				"fieldname": "setup_status_tab",
				"fieldtype": "Tab Break",
				"label": _("Setup Status"),
				"insert_after": "connections_tab",
			},
			{
				"fieldname": "employee_readiness_html",
				"fieldtype": "HTML",
				"insert_after": "setup_status_tab",
			},
			{
				"fieldname": "employment_type",
				"fieldtype": "Link",
				"ignore_user_permissions": 1,
				"label": _("Employment Type"),
				"options": "Employment Type",
				"insert_after": "department",
			},
			{
				"fieldname": "job_applicant",
				"fieldtype": "Link",
				"label": _("Job Applicant"),
				"options": "Job Applicant",
				"insert_after": "employment_details",
			},
			{
				"fieldname": "grade",
				"fieldtype": "Link",
				"label": _("Grade"),
				"options": "Employee Grade",
				"insert_after": "branch",
			},
			{
				"fieldname": "default_shift",
				"fieldtype": "Link",
				"label": _("Default Shift"),
				"options": "Shift Type",
				"insert_after": "holiday_list",
			},
			{
				"collapsible": 1,
				"fieldname": "health_insurance_section",
				"fieldtype": "Section Break",
				"label": _("Health Insurance"),
				"insert_after": "health_details",
			},
			{
				"fieldname": "health_insurance_provider",
				"fieldtype": "Link",
				"label": _("Health Insurance Provider"),
				"options": "Employee Health Insurance",
				"insert_after": "health_insurance_section",
			},
			{
				"depends_on": "eval:doc.health_insurance_provider",
				"fieldname": "health_insurance_no",
				"fieldtype": "Data",
				"label": _("Health Insurance No"),
				"insert_after": "health_insurance_provider",
			},
			{
				"fieldname": "father_or_husband_name",
				"fieldtype": "Data",
				"label": _("Father's / Husband's Name"),
				"insert_after": "marital_status",
				"description": _(
					"Name as printed on statutory records (PF, ESI, Form 16, gratuity). "
					"Use the husband's name for married women where applicable."
				),
			},
			{
				"fieldname": "approvers_section",
				"fieldtype": "Section Break",
				"label": _("Approvers"),
				"insert_after": "default_shift",
			},
			{
				"fieldname": "expense_approver",
				"fieldtype": "Link",
				"label": _("Expense Approver"),
				"options": "Employee",
				"insert_after": "approvers_section",
				"ignore_user_permissions": 1,
			},
			{
				"fieldname": "leave_approver",
				"fieldtype": "Link",
				"label": _("Leave Approver"),
				"options": "Employee",
				"insert_after": "expense_approver",
				"ignore_user_permissions": 1,
			},
			{
				"fieldname": "column_break_45",
				"fieldtype": "Column Break",
				"insert_after": "leave_approver",
			},
			{
				"fieldname": "shift_request_approver",
				"fieldtype": "Link",
				"label": _("Shift Request Approver"),
				"options": "Employee",
				"insert_after": "column_break_45",
				"ignore_user_permissions": 1,
			},
			{
				"fieldname": "salary_cb",
				"fieldtype": "Column Break",
				"insert_after": "salary_mode",
			},
			{
				"fetch_from": "department.payroll_cost_center",
				"fetch_if_empty": 1,
				"fieldname": "payroll_cost_center",
				"fieldtype": "Link",
				"label": _("Payroll Cost Center"),
				"options": "Cost Center",
				"insert_after": "salary_cb",
			},
			{
				"fieldname": "confirmation_status",
				"fieldtype": "Select",
				"label": _("Confirmation Status"),
				"options": "\nProbation\nConfirmed\nExtended\nReleased",
				"insert_after": "final_confirmation_date",
				"default": "",
				"description": _(
					"Probation: within probation period. Confirmed: passed probation. "
					"Extended: probation extended. Released: services terminated during probation."
				),
			},
			# --- Statutory IDs + UAN-Aadhaar seeding (SS Code §142) ---
			# Source of truth lives here, not only in the v15_0 patches. On fresh
			# installs (incl. every new SaaS tenant) and Frappe Cloud, post_model_sync
			# patches are stamped "applied" without running, so patch-only Custom
			# Fields never materialise. sync_custom_fields() runs on every migrate and
			# upserts these, so the columns self-heal regardless of Patch Log state.
			{
				"fieldname": "uan_number",
				"label": _("UAN"),
				"fieldtype": "Data",
				"length": 12,
				"insert_after": "provident_fund_account",
				"print_hide": 1,
				"translatable": 0,
				"description": _("12-digit EPFO Universal Account Number"),
			},
			{
				"fieldname": "esic_ip_number",
				"label": _("ESIC IP Number"),
				"fieldtype": "Data",
				"insert_after": "uan_number",
				"print_hide": 1,
				"translatable": 0,
			},
			{
				"fieldname": "aadhaar_number",
				"label": _("Aadhaar Number"),
				"fieldtype": "Data",
				"length": 12,
				"insert_after": "esic_ip_number",
				"print_hide": 1,
				"no_copy": 1,
				"translatable": 0,
				"description": _(
					"Full 12-digit Aadhaar — Verhoeff-checksum validated. "
					"Display masked elsewhere; last-4 auto-derived for audit views."
				),
			},
			{
				"fieldname": "aadhaar_last_4",
				"label": _("Aadhaar (last 4)"),
				"fieldtype": "Data",
				"length": 4,
				"insert_after": "aadhaar_number",
				"read_only": 1,
				"print_hide": 1,
				"translatable": 0,
				"description": _(
					"Auto-derived from the Aadhaar number above — retained for "
					"UAN-Aadhaar linkage and DPDP audit reports."
				),
			},
			{
				"fieldname": "nps_pran",
				"label": _("NPS PRAN"),
				"fieldtype": "Data",
				"insert_after": "aadhaar_last_4",
				"translatable": 0,
			},
			{
				"fieldname": "is_primary_employer",
				"label": _("Primary Employer for TDS / Form 12B"),
				"fieldtype": "Check",
				"insert_after": "nps_pran",
				"default": "0",
				"description": _("Only one Active Employee per User may be the Primary Employer."),
			},
			{
				# A "virtual" record exists ONLY to give a group manager standing in
				# this company (be a reports_to / department head / DRI / approver of
				# same-company people) — it is NOT an employment: no payroll, and it is
				# excluded from statutory headcount and subscription seat counts. At
				# least one record per person (same user / PAN / Aadhaar) must stay
				# real, so a human always has exactly one paid home. Enforced in
				# overrides.employee_master.validate_virtual_employee.
				"fieldname": "is_virtual_employee",
				"label": _("Virtual (Management-only) Employee"),
				"fieldtype": "Check",
				"insert_after": "is_primary_employer",
				"default": "0",
				"description": _(
					"Tick for a management-only record: no salary, excluded from statutory "
					"headcount &amp; billing. At least one record per person must stay real."
				),
			},
			{
				"fieldname": "labour_code_uan_section_break",
				"fieldtype": "Section Break",
				"label": _("UAN Aadhaar Seeding (SS Code §142)"),
				"insert_after": "is_virtual_employee",
				"collapsible": 1,
			},
			{
				"fieldname": "uan_aadhaar_linked",
				"fieldtype": "Check",
				"label": _("UAN Aadhaar Linked"),
				"insert_after": "labour_code_uan_section_break",
				"default": "0",
				"description": _("Per SS Code §142, UAN must be linked with Aadhaar."),
			},
			{
				"fieldname": "uan_linking_date",
				"fieldtype": "Date",
				"label": _("UAN Linking Date"),
				"insert_after": "uan_aadhaar_linked",
				"depends_on": "eval:doc.uan_aadhaar_linked",
			},
			{
				"fieldname": "uan_seeding_col_break",
				"fieldtype": "Column Break",
				"insert_after": "uan_linking_date",
			},
			{
				"fieldname": "uan_seeding_status",
				"fieldtype": "Select",
				"label": _("UAN Seeding Status"),
				"options": "Not Seeded\nPending\nSeeded\nMismatched",
				"insert_after": "uan_seeding_col_break",
				"default": "Not Seeded",
				"in_standard_filter": 1,
			},
			{
				"fieldname": "uan_seeding_attempts",
				"fieldtype": "Int",
				"label": _("UAN Seeding Attempts"),
				"insert_after": "uan_seeding_status",
				"default": "0",
				"non_negative": 1,
			},
		],
		"Attendance Request": [
			{
				"fieldname": "status",
				"fieldtype": "Select",
				"label": _("Status"),
				# Open (pending) → Approved (submitted) / Rejected (terminal) /
				# Needs Clarification (bounced back to employee). Cancelled = a
				# once-approved request that was later cancelled.
				"options": "Open\nApproved\nRejected\nNeeds Clarification\nCancelled",
				"default": "Open",
				"insert_after": "employee_name",
				"read_only": 1,
				"no_copy": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
				"allow_on_submit": 1,
			},
			{
				"fieldname": "attachment",
				"fieldtype": "Attach",
				"label": _("Supporting Document"),
				"insert_after": "explanation",
			},
			{
				"fieldname": "rejection_reason",
				"fieldtype": "Small Text",
				"label": _("Approver Remark"),
				"insert_after": "attachment",
				"read_only": 1,
				"no_copy": 1,
				"allow_on_submit": 1,
				"depends_on": "eval:['Rejected','Needs Clarification'].includes(doc.status)",
			},
		],
		"Project": [
			{
				"fieldname": "total_expense_claim",
				"fieldtype": "Currency",
				"label": _("Total Expense Claim (via Expense Claims)"),
				"read_only": 1,
				"insert_after": "total_costing_amount",
			},
		],
		"Appointment Letter": [
			{
				"fieldname": "letter_type",
				"fieldtype": "Select",
				"label": _("Letter Type"),
				"options": "Appointment\nConfirmation\nProbation Extension\nRelease\nOther",
				"default": "Appointment",
				"insert_after": "appointment_date",
				"in_list_view": 1,
				"in_standard_filter": 1,
			},
			{
				"fieldname": "probation_review",
				"fieldtype": "Link",
				"label": _("Probation Review"),
				"options": "Probation Review",
				"insert_after": "letter_type",
				"depends_on": "eval:in_list(['Confirmation','Probation Extension','Release'], doc.letter_type)",
				"read_only": 1,
			},
		],
		"Appointment Letter Template": [
			{
				"fieldname": "letter_type",
				"fieldtype": "Select",
				"label": _("Letter Type"),
				"options": "Appointment\nConfirmation\nProbation Extension\nRelease\nOther",
				"default": "Appointment",
				"insert_after": "template_name",
				"in_list_view": 1,
				"in_standard_filter": 1,
				"description": _(
					"Tag the template by the letter it produces. Used to filter "
					"template pickers (e.g., a Confirmation Letter sees only "
					"templates with letter_type=Confirmation)."
				),
			},
		],
		"Job Applicant": [
			{
				"fieldname": "is_internal_applicant",
				"fieldtype": "Check",
				"label": _("Internal Applicant"),
				"default": "0",
				"read_only": 1,
				"insert_after": "employee_referral",
				"in_list_view": 1,
				"in_standard_filter": 1,
				"description": _(
					"Set automatically when email_id matches an Active Employee. "
					"Internal applicants follow a different hiring workflow."
				),
			},
			{
				"fieldname": "source_employee",
				"fieldtype": "Link",
				"label": _("Source Employee"),
				"options": "Employee",
				"read_only": 1,
				"insert_after": "is_internal_applicant",
				"description": _("Existing Employee record matched by email_id."),
			},
		],
		"Appraisal": [
			{
				"fieldname": "kra_performance_section",
				"fieldtype": "Section Break",
				"label": _("KRA Performance from Task Instances (Auto)"),
				"insert_after": "appraisal_kra",
				"collapsible": 1,
				"description": _(
					"Computed from this Employee's Task Instances (Goal records "
					"with goal_type='Task Instance') in the cycle period. Refreshed "
					"on each save of this Appraisal."
				),
			},
			{
				"fieldname": "kra_performance_html",
				"fieldtype": "HTML",
				"label": _("KRA Performance HTML"),
				"insert_after": "kra_performance_section",
			},
		],
		"Goal": [
			{
				"fieldname": "delegated_from",
				"fieldtype": "Link",
				"label": _("Delegated From"),
				"options": "Employee",
				"insert_after": "status",
				"read_only": 1,
				"description": _("Original assignee — set when a task is routed to the manager for leave cover."),
			},
			{
				"fieldname": "performed_by",
				"fieldtype": "Link",
				"label": _("Performed By"),
				"options": "Employee",
				"insert_after": "delegated_from",
				"description": _("Who actually performed the task (captured when a delegated task is completed)."),
			},
			{
				"fieldname": "accountable_parent",
				"fieldtype": "Link",
				"label": _("Accountable Parent"),
				"options": "Goal",
				"insert_after": "performed_by",
				"read_only": 1,
				"description": _(
					"The head's Accountable instance this child was split from (Distribute). "
					"The parent auto-completes when all its children are done."
				),
			},
			{
				"fieldname": "goal_type",
				"fieldtype": "Select",
				"label": _("Goal Type"),
				"options": "SMART\nTask Instance",
				"default": "SMART",
				"insert_after": "status",
				"in_list_view": 1,
				"in_standard_filter": 1,
				"description": _(
					"SMART = traditional achieve-X-by-Y goal. Task Instance = "
					"one occurrence of a recurring HRMS Task, created by the "
					"scheduler. Different list views, different lifecycles."
				),
			},
			{
				"fieldname": "task_template",
				"fieldtype": "Link",
				"label": _("Task Template"),
				"options": "HRMS Task",
				"insert_after": "goal_type",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
				"in_standard_filter": 1,
				"description": _("Set only for Task Instances — points to the HRMS Task definition."),
			},
			{
				"fieldname": "period_label",
				"fieldtype": "Data",
				"label": _("Period Label"),
				"insert_after": "task_template",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
				"description": _("E.g. '2026-05-29' (daily) / 'Week 22 2026' / 'May 2026' / 'Q2 2026' / '2026'."),
			},
			{
				"fieldname": "due_date",
				"fieldtype": "Date",
				"label": _("Due Date"),
				"insert_after": "period_label",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
			},
			{
				"fieldname": "completion_type",
				"fieldtype": "Data",
				"label": _("Completion Type"),
				"fetch_from": "task_template.completion_type",
				"read_only": 1,
				"insert_after": "due_date",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
			},
			{
				"fieldname": "task_attachment",
				"fieldtype": "Attach",
				"label": _("Attachment"),
				"insert_after": "completion_type",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
			},
			{
				"fieldname": "numeric_value",
				"fieldtype": "Float",
				"label": _("Numeric Value (for KPI)"),
				"insert_after": "task_attachment",
				"depends_on": "eval:doc.goal_type=='Task Instance' && doc.completion_type=='Numeric Entry'",
			},
			{
				"fieldname": "task_notes",
				"fieldtype": "Small Text",
				"label": _("Notes"),
				"insert_after": "numeric_value",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
			},
			{
				"fieldname": "approver_user",
				"fieldtype": "Link",
				"label": _("Approver"),
				"options": "User",
				"insert_after": "task_notes",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
				"description": _("Computed on submit if Task requires approval."),
			},
			{
				"fieldname": "approver_role",
				"fieldtype": "Link",
				"label": _("Approver Role"),
				"options": "Role",
				"insert_after": "approver_user",
				"read_only": 1,
				"depends_on": "eval:doc.goal_type=='Task Instance'",
				"description": _(
					"Set when the Task routes approval to a Role — ANY holder of this role "
					"may approve, so accountability survives that person leaving."
				),
			},
			{
				"fieldname": "submitted_at",
				"fieldtype": "Datetime",
				"label": _("Submitted At"),
				"read_only": 1,
				"insert_after": "approver_role",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
			},
			{
				"fieldname": "submitted_by",
				"fieldtype": "Link",
				"label": _("Submitted By"),
				"options": "User",
				"read_only": 1,
				"insert_after": "submitted_at",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
			},
			{
				"fieldname": "approved_at",
				"fieldtype": "Datetime",
				"label": _("Approved At"),
				"read_only": 1,
				"insert_after": "submitted_by",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
			},
			{
				"fieldname": "approved_by",
				"fieldtype": "Link",
				"label": _("Approved By"),
				"options": "User",
				"read_only": 1,
				"insert_after": "approved_at",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
			},
			{
				"fieldname": "approval_notes",
				"fieldtype": "Small Text",
				"label": _("Approval Notes"),
				"insert_after": "approved_by",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
			},
			{
				"fieldname": "last_reminder_sent_on",
				"fieldtype": "Date",
				"label": _("Last Overdue Reminder Sent On"),
				"read_only": 1,
				"insert_after": "approval_notes",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
			},
			{
				"fieldname": "lead_reminder_sent_on",
				"fieldtype": "Date",
				"label": _("Lead Reminder Sent On"),
				"read_only": 1,
				"insert_after": "last_reminder_sent_on",
				"depends_on": "eval:doc.goal_type=='Task Instance'",
			},
		],
		"Task": [
			{
				"fieldname": "total_expense_claim",
				"fieldtype": "Currency",
				"label": _("Total Expense Claim (via Expense Claim)"),
				"options": "Company:company:default_currency",
				"read_only": 1,
				"insert_after": "total_costing_amount",
			},
		],
		"Timesheet": [
			{
				"fieldname": "salary_slip",
				"fieldtype": "Link",
				"label": _("Salary Slip"),
				"no_copy": 1,
				"options": "Salary Slip",
				"print_hide": 1,
				"read_only": 1,
				"insert_after": "column_break_3",
			},
		],
		"Terms and Conditions": [
			{
				"default": "1",
				"fieldname": "hr",
				"fieldtype": "Check",
				"label": _("HR"),
				"insert_after": "buying",
			},
		],
		# Phase 5 Grievance enhancement. These were originally shipped via the
		# one-shot patch v15_0/enhance_employee_grievance; kept here so they
		# self-heal on every migrate (a site that lost them — the classic prod /
		# Frappe Cloud drift — gets them back instead of the grievance form
		# crashing on a missing `default_severity` / `severity` column).
		"Employee Grievance": [
			{
				"fieldname": "company",
				"fieldtype": "Link",
				"options": "Company",
				"label": _("Company"),
				"insert_after": "raised_by",
				"reqd": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
				"fetch_from": "raised_by.company",
				"description": _("Every Grievance lives in exactly one Company."),
			},
			{
				"fieldname": "severity",
				"fieldtype": "Select",
				"label": _("Severity"),
				"options": "Low\nMedium\nHigh\nCritical",
				"default": "Medium",
				"insert_after": "status",
				"in_list_view": 1,
				"in_standard_filter": 1,
				"description": _("Drives SLA defaults + escalation cadence from HR Settings."),
			},
			{
				"fieldname": "workflow_state",
				"fieldtype": "Link",
				"options": "Workflow State",
				"label": _("Workflow State"),
				"insert_after": "severity",
				"no_copy": 1,
				"read_only": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
			},
			{
				"fieldname": "sla_due_date",
				"fieldtype": "Date",
				"label": _("SLA Due Date"),
				"insert_after": "workflow_state",
				"read_only": 1,
				"description": _(
					"Auto-set from date + severity SLA days. Past this date, SLA scheduler escalates."
				),
			},
			{
				"fieldname": "last_reminder_sent_on",
				"fieldtype": "Date",
				"label": _("Last Reminder Sent On"),
				"insert_after": "sla_due_date",
				"read_only": 1,
				"no_copy": 1,
				"hidden": 1,
			},
			{
				"fieldname": "linked_disciplinary_action",
				"fieldtype": "Link",
				"options": "Disciplinary Action",
				"label": _("Linked Disciplinary Action"),
				"insert_after": "resolution_detail",
				"read_only": 1,
				"description": _(
					"Auto-linked when this grievance leads to a Disciplinary Action."
				),
			},
		],
		"Grievance Type": [
			{
				"fieldname": "default_severity",
				"fieldtype": "Select",
				"label": _("Default Severity"),
				"options": "Low\nMedium\nHigh\nCritical",
				"default": "Medium",
				"insert_after": "description",
				"description": _(
					"Applied to new Grievances of this type when severity isn't set explicitly."
				),
			},
			{
				"fieldname": "default_sla_days",
				"fieldtype": "Int",
				"label": _("Default SLA (days)"),
				"insert_after": "default_severity",
				"non_negative": 1,
				"description": _(
					"Days from raised_date by which a grievance of this type must be resolved. "
					"Overrides HR Settings severity defaults."
				),
			},
		],
	}


def make_fixtures():
	records = [
		# expense claim type
		{"doctype": "Expense Claim Type", "name": _("Calls"), "expense_type": _("Calls")},
		{"doctype": "Expense Claim Type", "name": _("Food"), "expense_type": _("Food")},
		{"doctype": "Expense Claim Type", "name": _("Medical"), "expense_type": _("Medical")},
		{"doctype": "Expense Claim Type", "name": _("Others"), "expense_type": _("Others")},
		{"doctype": "Expense Claim Type", "name": _("Travel"), "expense_type": _("Travel")},
		# vehicle service item
		{"doctype": "Vehicle Service Item", "service_item": "Brake Oil"},
		{"doctype": "Vehicle Service Item", "service_item": "Brake Pad"},
		{"doctype": "Vehicle Service Item", "service_item": "Clutch Plate"},
		{"doctype": "Vehicle Service Item", "service_item": "Engine Oil"},
		{"doctype": "Vehicle Service Item", "service_item": "Oil Change"},
		{"doctype": "Vehicle Service Item", "service_item": "Wheels"},
		# leave type
		{
			"doctype": "Leave Type",
			"leave_type_name": _("Casual Leave"),
			"name": _("Casual Leave"),
			"allow_encashment": 1,
			"is_carry_forward": 1,
			"max_continuous_days_allowed": "3",
			"include_holiday": 1,
		},
		{
			"doctype": "Leave Type",
			"leave_type_name": _("Compensatory Off"),
			"name": _("Compensatory Off"),
			"allow_encashment": 0,
			"is_carry_forward": 0,
			"include_holiday": 1,
			"is_compensatory": 1,
		},
		{
			"doctype": "Leave Type",
			"leave_type_name": _("Sick Leave"),
			"name": _("Sick Leave"),
			"allow_encashment": 0,
			"is_carry_forward": 0,
			"include_holiday": 1,
		},
		{
			"doctype": "Leave Type",
			"leave_type_name": _("Privilege Leave"),
			"name": _("Privilege Leave"),
			"allow_encashment": 0,
			"is_carry_forward": 0,
			"include_holiday": 1,
		},
		{
			"doctype": "Leave Type",
			"leave_type_name": _("Leave Without Pay"),
			"name": _("Leave Without Pay"),
			"allow_encashment": 0,
			"is_carry_forward": 0,
			"is_lwp": 1,
			"include_holiday": 1,
		},
		# Employment Type
		{"doctype": "Employment Type", "employee_type_name": _("Full-time")},
		{"doctype": "Employment Type", "employee_type_name": _("Part-time")},
		{"doctype": "Employment Type", "employee_type_name": _("Probation")},
		{"doctype": "Employment Type", "employee_type_name": _("Contract")},
		{"doctype": "Employment Type", "employee_type_name": _("Commission")},
		{"doctype": "Employment Type", "employee_type_name": _("Piecework")},
		{"doctype": "Employment Type", "employee_type_name": _("Intern")},
		{"doctype": "Employment Type", "employee_type_name": _("Apprentice")},
		# Job Applicant Source
		{"doctype": "Job Applicant Source", "source_name": _("Website Listing")},
		{"doctype": "Job Applicant Source", "source_name": _("Walk In")},
		{"doctype": "Job Applicant Source", "source_name": _("Employee Referral")},
		{"doctype": "Job Applicant Source", "source_name": _("Campaign")},
		# Offer Term
		{"doctype": "Offer Term", "offer_term": _("Date of Joining")},
		{"doctype": "Offer Term", "offer_term": _("Annual Salary")},
		{"doctype": "Offer Term", "offer_term": _("Probationary Period")},
		{"doctype": "Offer Term", "offer_term": _("Employee Benefits")},
		{"doctype": "Offer Term", "offer_term": _("Working Hours")},
		{"doctype": "Offer Term", "offer_term": _("Stock Options")},
		{"doctype": "Offer Term", "offer_term": _("Department")},
		{"doctype": "Offer Term", "offer_term": _("Job Description")},
		{"doctype": "Offer Term", "offer_term": _("Responsibilities")},
		{"doctype": "Offer Term", "offer_term": _("Leaves per Year")},
		{"doctype": "Offer Term", "offer_term": _("Notice Period")},
		{"doctype": "Offer Term", "offer_term": _("Incentives")},
		# Email Account
		{"doctype": "Email Account", "email_id": "jobs@example.com", "append_to": "Job Applicant"},
	]

	make_records(records)


def setup_notifications():
	base_path = frappe.get_app_path("indian_hrms_compliance", "hr", "doctype")

	# Leave Application
	records = [
		{
			"doctype": "Email Template",
			"name": _("Default Leave Approval Notification"),
			"response": frappe.read_file(
				os.path.join(base_path, "leave_application/leave_approval_notification_template.html")
			),
			"subject": _("Leave Approval Request from {{ employee_name }} — {{ company }}"),
			"owner": frappe.session.user,
		}
	]
	records += [
		{
			"doctype": "Email Template",
			"name": _("Default Leave Status Notification"),
			"response": frappe.read_file(
				os.path.join(base_path, "leave_application/leave_status_notification_template.html")
			),
			"subject": _("Your Leave Application has been {{ status }} — {{ company }}"),
			"owner": frappe.session.user,
		}
	]

	# Interview
	response = frappe.read_file(
		os.path.join(base_path, "interview/interview_reminder_notification_template.html")
	)
	records += [
		{
			"doctype": "Email Template",
			"name": _("Interview Reminder"),
			"response": response,
			"subject": _("Interview Reminder"),
			"owner": frappe.session.user,
		}
	]
	response = frappe.read_file(
		os.path.join(base_path, "interview/interview_feedback_reminder_template.html")
	)
	records += [
		{
			"doctype": "Email Template",
			"name": _("Interview Feedback Reminder"),
			"response": response,
			"subject": _("Interview Feedback Reminder"),
			"owner": frappe.session.user,
		}
	]

	# Exit Interview
	response = frappe.read_file(
		os.path.join(base_path, "exit_interview/exit_questionnaire_notification_template.html")
	)
	records += [
		{
			"doctype": "Email Template",
			"name": _("Exit Questionnaire Notification"),
			"response": response,
			"subject": _("Exit Questionnaire Notification"),
			"owner": frappe.session.user,
		}
	]

	make_records(records)


def update_hr_defaults():
	hr_settings = frappe.get_doc("HR Settings")
	hr_settings.emp_created_by = "Naming Series"
	hr_settings.leave_approval_notification_template = _("Default Leave Approval Notification")
	hr_settings.leave_status_notification_template = _("Default Leave Status Notification")

	hr_settings.send_interview_reminder = 1
	hr_settings.interview_reminder_template = _("Interview Reminder")
	hr_settings.remind_before = "00:15:00"

	hr_settings.send_interview_feedback_reminder = 1
	hr_settings.feedback_reminder_notification_template = _("Interview Feedback Reminder")

	hr_settings.exit_questionnaire_notification_template = _("Exit Questionnaire Notification")
	hr_settings.save()


def set_single_defaults():
	for dt in ("HR Settings", "Payroll Settings"):
		default_values = frappe.get_all(
			"DocField",
			filters={"parent": dt},
			fields=["fieldname", "default"],
			as_list=True,
		)
		if default_values:
			try:
				doc = frappe.get_doc(dt, dt)
				for fieldname, value in default_values:
					doc.set(fieldname, value)
				doc.flags.ignore_mandatory = True
				doc.save()
			except frappe.ValidationError:
				pass


def create_default_role_profiles():
	for role_profile_name, roles in DEFAULT_ROLE_PROFILES.items():
		if frappe.db.exists("Role Profile", role_profile_name):
			continue

		role_profile = frappe.new_doc("Role Profile")
		role_profile.role_profile = role_profile_name
		for role in roles:
			role_profile.append("roles", {"role": role})

		role_profile.insert(ignore_permissions=True)


def get_post_install_patches():
	return (
		"erpnext.patches.v13_0.move_tax_slabs_from_payroll_period_to_income_tax_slab",
		"erpnext.patches.v13_0.move_doctype_reports_and_notification_from_hr_to_payroll",
		"erpnext.patches.v13_0.move_payroll_setting_separately_from_hr_settings",
		"erpnext.patches.v13_0.update_start_end_date_for_old_shift_assignment",
		"erpnext.patches.v13_0.updates_for_multi_currency_payroll",
		"erpnext.patches.v13_0.update_reason_for_resignation_in_employee",
		"erpnext.patches.v13_0.set_company_in_leave_ledger_entry",
		"erpnext.patches.v13_0.rename_stop_to_send_birthday_reminders",
		"erpnext.patches.v13_0.set_training_event_attendance",
		"erpnext.patches.v14_0.set_payroll_cost_centers",
		"erpnext.patches.v13_0.update_employee_advance_status",
		"erpnext.patches.v13_0.update_expense_claim_status_for_paid_advances",
		"erpnext.patches.v14_0.delete_employee_transfer_property_doctype",
		"erpnext.patches.v13_0.set_payroll_entry_status",
		# HRMS
		"create_country_fixtures",
		"update_allocate_on_in_leave_type",
		"update_performance_module_changes",
	)


def run_post_install_patches():
	print("\nPatching Existing Data...")

	POST_INSTALL_PATCHES = get_post_install_patches()
	frappe.flags.in_patch = True

	try:
		for patch in POST_INSTALL_PATCHES:
			patch_name = patch.split(".")[-1]
			if not patch_name:
				continue

			frappe.get_attr(f"indian_hrms_compliance.patches.post_install.{patch_name}.execute")()
	finally:
		frappe.flags.in_patch = False


# LENDING APP SETUP & CLEANUP
def create_salary_slip_loan_fields():
	if "lending" in frappe.get_installed_apps():
		create_custom_fields(get_salary_slip_loan_fields(), ignore_validate=True)


def add_lending_docperms_to_ess():
	doc = frappe.get_doc("User Type", "Employee Self Service")

	loan_docperms = get_lending_docperms_for_ess()
	append_docperms_to_user_type(loan_docperms, doc)

	doc.flags.ignore_links = True
	doc.save(ignore_permissions=True)


def remove_lending_docperms_from_ess():
	doc = frappe.get_doc("User Type", "Employee Self Service")

	loan_docperms = get_lending_docperms_for_ess()

	for row in list(doc.user_doctypes):
		if row.document_type in loan_docperms:
			doc.user_doctypes.remove(row)

	doc.flags.ignore_links = True
	doc.save(ignore_permissions=True)


# ESS USER TYPE SETUP & CLEANUP
def add_non_standard_user_types():
	user_types = get_user_types_data()

	for user_type, data in user_types.items():
		create_custom_role(data)
		create_user_type(user_type, data)


def get_user_types_data():
	return {
		"Employee Self Service": {
			"role": "Employee Self Service",
			"apply_user_permission_on": "Employee",
			"user_id_field": "user_id",
			"doctypes": {
				# masters
				"Holiday List": ["read"],
				"Employee": ["read", "write"],
				"Company": ["read"],
				# payroll
				"Salary Slip": ["read"],
				"Employee Benefit Application": ["read", "write", "create", "delete"],
				# expenses
				"Expense Claim": ["read", "write", "create", "delete"],
				"Expense Claim Type": ["read"],
				"Employee Advance": ["read", "write", "create", "delete"],
				# leave and attendance
				"Leave Type": ["read"],
				"Leave Application": ["read", "write", "create", "delete"],
				"Attendance Request": ["read", "write", "create", "delete"],
				"Compensatory Leave Request": ["read", "write", "create", "delete"],
				# tax
				"Employee Tax Exemption Declaration": ["read", "write", "create", "delete"],
				"Employee Tax Exemption Proof Submission": ["read", "write", "create", "delete"],
				# projects
				"Timesheet": ["read", "write", "create", "delete", "submit", "cancel", "amend"],
				# trainings
				"Training Program": ["read"],
				"Training Feedback": ["read", "write", "create", "delete", "submit", "cancel", "amend"],
				# shifts
				"Employee Checkin": ["read"],
				"Shift Request": ["read", "write", "create", "delete", "submit", "cancel", "amend"],
				# misc
				"Employee Grievance": ["read", "write", "create", "delete"],
				"Employee Referral": ["read", "write", "create", "delete"],
				"Travel Request": ["read", "write", "create", "delete"],
			},
		}
	}


def get_lending_docperms_for_ess():
	return {
		"Loan": ["read"],
		"Loan Application": ["read", "write", "create", "delete", "submit"],
		"Loan Product": ["read"],
	}


def create_custom_role(data):
	if data.get("role") and not frappe.db.exists("Role", data.get("role")):
		frappe.get_doc(
			{"doctype": "Role", "role_name": data.get("role"), "desk_access": 1, "is_custom": 1}
		).insert(ignore_permissions=True)


def create_user_type(user_type, data):
	if frappe.db.exists("User Type", user_type):
		doc = frappe.get_cached_doc("User Type", user_type)
		doc.user_doctypes = []
	else:
		doc = frappe.new_doc("User Type")
		doc.update(
			{
				"name": user_type,
				"role": data.get("role"),
				"user_id_field": data.get("user_id_field"),
				"apply_user_permission_on": data.get("apply_user_permission_on"),
			}
		)

	docperms = data.get("doctypes")
	if doc.role == "Employee Self Service" and "lending" in frappe.get_installed_apps():
		docperms.update(get_lending_docperms_for_ess())

	append_docperms_to_user_type(docperms, doc)

	doc.flags.ignore_links = True
	doc.save(ignore_permissions=True)


def append_docperms_to_user_type(docperms, doc):
	existing_doctypes = [d.document_type for d in doc.user_doctypes]

	for doctype, perms in docperms.items():
		if doctype in existing_doctypes:
			continue

		args = {"document_type": doctype}
		for perm in perms:
			args[perm] = 1

		doc.append("user_doctypes", args)


def update_select_perm_after_install():
	if not frappe.flags.update_select_perm_after_migrate:
		return

	frappe.flags.ignore_select_perm = False
	for row in frappe.get_all("User Type", filters={"is_standard": 0}):
		print("Updating user type :- ", row.name)
		doc = frappe.get_doc("User Type", row.name)
		doc.flags.ignore_links = True
		doc.save()

	frappe.flags.update_select_perm_after_migrate = False


def delete_custom_fields(custom_fields: dict):
	"""
	:param custom_fields: a dict like `{'Salary Slip': [{fieldname: 'loans', ...}]}`
	"""
	for doctype, fields in custom_fields.items():
		frappe.db.delete(
			"Custom Field",
			{
				"fieldname": ("in", [field["fieldname"] for field in fields]),
				"dt": doctype,
			},
		)

		frappe.clear_cache(doctype=doctype)


DEFAULT_ROLE_PROFILES = {
	"HR": [
		"HR User",
		"HR Manager",
		"Leave Approver",
		"Expense Approver",
	],
}


def get_salary_slip_loan_fields():
	return {
		"Salary Slip": [
			{
				"fieldname": "loan_repayment_sb_1",
				"fieldtype": "Section Break",
				"label": _("Loan Repayment"),
				"depends_on": "total_loan_repayment",
				"insert_after": "base_total_deduction",
			},
			{
				"fieldname": "loans",
				"fieldtype": "Table",
				"label": _("Employee Loan"),
				"options": "Salary Slip Loan",
				"print_hide": 1,
				"insert_after": "loan_repayment_sb_1",
			},
			{
				"fieldname": "loan_details_sb_1",
				"fieldtype": "Section Break",
				"depends_on": "eval:doc.docstatus != 0",
				"insert_after": "loans",
			},
			{
				"fieldname": "total_principal_amount",
				"fieldtype": "Currency",
				"label": _("Total Principal Amount"),
				"default": "0",
				"options": "Company:company:default_currency",
				"read_only": 1,
				"insert_after": "loan_details_sb_1",
			},
			{
				"fieldname": "total_interest_amount",
				"fieldtype": "Currency",
				"label": _("Total Interest Amount"),
				"default": "0",
				"options": "Company:company:default_currency",
				"read_only": 1,
				"insert_after": "total_principal_amount",
			},
			{
				"fieldname": "loan_cb_1",
				"fieldtype": "Column Break",
				"insert_after": "total_interest_amount",
			},
			{
				"fieldname": "total_loan_repayment",
				"fieldtype": "Currency",
				"label": _("Total Loan Repayment"),
				"default": "0",
				"options": "Company:company:default_currency",
				"read_only": 1,
				"insert_after": "loan_cb_1",
			},
		],
		"Loan": [
			{
				"default": "0",
				"depends_on": 'eval:doc.applicant_type=="Employee"',
				"fieldname": "repay_from_salary",
				"fieldtype": "Check",
				"label": _("Repay From Salary"),
				"insert_after": "status",
			},
		],
		"Loan Repayment": [
			{
				"default": "0",
				"fieldname": "repay_from_salary",
				"fieldtype": "Check",
				"label": _("Repay From Salary"),
				"insert_after": "is_term_loan",
			},
			{
				"depends_on": "eval:doc.repay_from_salary",
				"fieldname": "payroll_payable_account",
				"fieldtype": "Link",
				"label": _("Payroll Payable Account"),
				"mandatory_depends_on": "eval:doc.repay_from_salary",
				"options": "Account",
				"insert_after": "payment_account",
			},
			{
				"default": "0",
				"depends_on": 'eval:doc.applicant_type=="Employee"',
				"fieldname": "process_payroll_accounting_entry_based_on_employee",
				"hidden": 1,
				"fieldtype": "Check",
				"label": _("Process Payroll Accounting Entry based on Employee"),
				"insert_after": "repay_from_salary",
			},
		],
	}
