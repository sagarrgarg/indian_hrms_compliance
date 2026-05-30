# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Salary Structure Validator — Phase 6A.

Runs 10 statutory checks against a Salary Structure (and its Assignments)
on save. Each check returns either None (clean) or a tuple
``(severity, code, message)``.

Severities:
  * HARD — throws unless HR Settings.wage_code_enforcement == "OFF".
    Blocks save.
  * WARN — msgprint, doesn't block.
  * INFO — quiet msgprint (alert style).

Every issue is also appended to the Salary Structure Validation Log so
HR retains an audit trail across saves.

Reads HR Settings via ``_hr_setting()`` so the validator ships cleanly
even if the Statutory tab hasn't been added yet — defaults flow through.

Wired in hooks.py:
  doc_events["Salary Structure"]["validate"]
    = "...salary_structure_validator.validate_salary_structure"
  doc_events["Salary Structure Assignment"]["validate"]
    = "...salary_structure_validator.validate_salary_structure_assignment"
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from indian_hrms_compliance.hr.doctype.statutory_component_mapping.statutory_component_mapping import (
	get_mapping_for_company,
)
from indian_hrms_compliance.hr.doctype.minimum_wage_notification.minimum_wage_notification import (
	get_effective_minimum_wage,
	derive_effective_monthly_floor,
)
from indian_hrms_compliance.hr.doctype.salary_structure_validation_log.salary_structure_validation_log import (
	record_issue,
)


# Defaults mirror the verified 2026 statutory facts from Phase 6A brief.
HR_SETTINGS_DEFAULTS = {
	"wage_code_enforcement": "HARD",
	"wage_code_basic_da_min_pct": 50.0,
	"pf_wage_ceiling": 15000,
	"pf_employee_rate_pct": 12.0,
	"pf_employer_rate_pct": 12.0,
	"pf_eps_rate_pct": 8.33,
	"pf_edli_rate_pct": 0.50,
	"pf_admin_charges_pct": 0.50,
	"pf_admin_charges_min": 500,
	"pf_minimum_headcount_for_applicability": 20,
	"esi_wage_ceiling": 21000,
	"esi_wage_ceiling_disabled": 25000,
	"esi_employee_rate_pct": 0.75,
	"esi_employer_rate_pct": 3.25,
	"esi_employee_daily_wage_waiver": 176,
	"enforce_minimum_wage_validation": 1,
	"dpdp_aadhaar_consent_required": 1,
	"dpdp_data_retention_years": 8,
}


def _hr_setting(field, default=None):
	"""Safe HR Settings read — returns default if the field doesn't exist
	yet. Same pattern as overrides/full_and_final_extension and
	overrides/grievance_workflow. Falls back to HR_SETTINGS_DEFAULTS when
	the field is missing AND no default is passed."""
	meta = frappe.get_meta("HR Settings")
	if not meta.get_field(field):
		if default is not None:
			return default
		return HR_SETTINGS_DEFAULTS.get(field)
	val = frappe.db.get_single_value("HR Settings", field)
	if val in (None, ""):
		if default is not None:
			return default
		return HR_SETTINGS_DEFAULTS.get(field)
	return val


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def validate_salary_structure(doc, method=None):
	"""doc_event on Salary Structure.validate — runs every structure-level
	check, aggregates issues, logs them, and throws on HARDs."""
	# Skip validation for cancelled / templates / no-component drafts.
	if doc.docstatus == 2:
		return
	if not (doc.earnings or doc.deductions):
		return

	issues = []
	for fn in STRUCTURE_LEVEL_CHECKS:
		try:
			result = fn(doc)
		except Exception:
			frappe.log_error(
				title=f"SSV check {fn.__name__} crashed on {doc.name or '(new)'}",
				message=frappe.get_traceback(),
			)
			continue
		if not result:
			continue
		if isinstance(result, list):
			issues.extend(result)
		else:
			issues.append(result)

	_dispatch_issues(doc, issues)


def validate_salary_structure_assignment(doc, method=None):
	"""doc_event on Salary Structure Assignment.validate — runs the
	assignment-level checks (statutory IDs, income tax slab, DPDP)."""
	if doc.docstatus == 2:
		return

	issues = []
	for fn in ASSIGNMENT_LEVEL_CHECKS:
		try:
			result = fn(doc)
		except Exception:
			frappe.log_error(
				title=f"SSV-A check {fn.__name__} crashed on {doc.name or '(new)'}",
				message=frappe.get_traceback(),
			)
			continue
		if not result:
			continue
		if isinstance(result, list):
			issues.extend(result)
		else:
			issues.append(result)

	# Log against the parent Salary Structure (so HR sees all issues for a
	# structure in one list).
	target = doc.salary_structure or doc.name
	_dispatch_issues_with_target(target, issues)


def _dispatch_issues(doc, issues):
	target = doc.name or doc.salary_structure_name
	_dispatch_issues_with_target(target, issues)


def _dispatch_issues_with_target(target, issues):
	if not issues:
		return

	hards = [i for i in issues if i[0] == "HARD"]
	warns = [i for i in issues if i[0] == "WARN"]
	infos = [i for i in issues if i[0] == "INFO"]

	# Persist every issue to the log (best-effort, never raises).
	if target:
		for sev, code, msg in issues:
			record_issue(target, sev, code, msg)

	enforcement = (_hr_setting("wage_code_enforcement", "HARD") or "HARD").upper()

	if hards and enforcement != "OFF":
		formatted = "\n".join(f"  [{code}] {msg}" for _, code, msg in hards)
		frappe.throw(
			_("Salary Structure validation failed with {0} HARD issue(s):\n{1}").format(
				len(hards), formatted
			),
			title=_("Statutory Compliance"),
		)

	for sev, code, msg in warns:
		frappe.msgprint(
			_("[{0}] {1}").format(code, msg),
			title=_("Statutory Warning"),
			indicator="orange",
			alert=True,
		)
	for sev, code, msg in infos:
		frappe.msgprint(
			_("[{0}] {1}").format(code, msg),
			indicator="blue",
			alert=True,
		)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sum_amounts(rows):
	return sum(flt(r.amount) for r in (rows or []))


def _component_names(rows):
	return {r.salary_component for r in (rows or []) if r.salary_component}


def _earnings_total_monthly(doc):
	"""Approximate monthly total from earnings rows. If the structure
	defines amounts as formulas, falls back to the raw amount.

	Frappe stores amount_based_on_formula structures as formulas but the
	default amount column is still set when previewing — for the validator
	we trust whatever is in row.amount."""
	return _sum_amounts(doc.earnings)


def _basic_plus_da(doc, mapping=None):
	"""Returns the monthly sum of Basic + DA rows. Uses Statutory Component
	Mapping when available; falls back to substring matching."""
	basic_names = set()
	da_names = set()
	if mapping:
		if mapping.basic_component:
			basic_names.add(mapping.basic_component)
		if mapping.da_component:
			da_names.add(mapping.da_component)
	total = 0
	for row in doc.earnings or []:
		comp = row.salary_component or ""
		if comp in basic_names or comp in da_names:
			total += flt(row.amount)
			continue
		# Fallback substring match — case-insensitive
		lower = comp.lower()
		if not (basic_names or da_names):
			if "basic" in lower or "dearness" in lower or lower == "da":
				total += flt(row.amount)
	return total


def _state_from_employee_or_company(doc):
	"""Resolve an Indian State for this Salary Structure. Tries each
	Assignment's Employee → company → state default, finally HR Settings
	default_pt_state. Returns the Indian State.name or None."""
	# Check existing assignments
	assignments = frappe.get_all(
		"Salary Structure Assignment",
		filters={"salary_structure": doc.name, "docstatus": ("!=", 2)},
		fields=["employee", "company"],
		limit=10,
	)
	for a in assignments:
		state = _state_for_employee(a.employee)
		if state:
			return state

	# Try the Company on the Salary Structure
	if doc.company:
		state = _state_for_company(doc.company)
		if state:
			return state

	# Fall back to HR Settings default
	return _hr_setting("default_pt_state")


def _state_for_employee(employee):
	"""Resolve an Indian State for an Employee — uses their address
	state, else their Company's address state, else None."""
	if not employee:
		return None
	# Employee may have a permanent_address / current_address (linked Address)
	addr_state = frappe.db.get_value(
		"Address",
		{
			"address_title": ("like", f"%{employee}%"),
		},
		"state",
	)
	if addr_state:
		matched = _match_state(addr_state)
		if matched:
			return matched
	emp_company = frappe.db.get_value("Employee", employee, "company")
	if emp_company:
		return _state_for_company(emp_company)
	return None


def _state_for_company(company):
	"""Best-effort state lookup for a Company. Reads Address linked via
	Dynamic Link from Address → Company."""
	addr = frappe.db.sql(
		"""
		SELECT a.state
		FROM `tabAddress` a
		JOIN `tabDynamic Link` dl ON dl.parent = a.name
		WHERE dl.link_doctype = 'Company' AND dl.link_name = %s
		LIMIT 1
		""",
		company,
		as_dict=True,
	)
	if addr and addr[0].state:
		return _match_state(addr[0].state)
	return None


def _match_state(state_text):
	"""Match a free-text state name to an Indian State.name (state_code)."""
	if not state_text:
		return None
	state_text = state_text.strip()
	# Try exact match on state_name first
	match = frappe.db.get_value("Indian State", {"state_name": state_text}, "name")
	if match:
		return match
	# Try fuzzy contains
	match = frappe.db.get_value(
		"Indian State", {"state_name": ("like", f"%{state_text}%")}, "name"
	)
	return match


def _company_headcount(company):
	if not company:
		return 0
	return frappe.db.count("Employee", {"company": company, "status": "Active"})


# ---------------------------------------------------------------------------
# Structure-level checks
# ---------------------------------------------------------------------------


def check_wage_code_50_rule(doc):
	"""Basic + DA ≥ 50% of total earnings (Wage Code §2(y) effective
	21 Nov 2025). Severity from HR Settings.wage_code_enforcement."""
	mapping = get_mapping_for_company(doc.company) if doc.company else None
	total = _earnings_total_monthly(doc)
	if not total:
		return None
	basic_da = _basic_plus_da(doc, mapping=mapping)
	pct_floor = flt(_hr_setting("wage_code_basic_da_min_pct", 50.0))
	actual_pct = (basic_da / total) * 100 if total else 0
	if actual_pct + 0.001 >= pct_floor:
		return None
	severity = (_hr_setting("wage_code_enforcement", "HARD") or "HARD").upper()
	if severity not in ("HARD", "WARN", "INFO", "OFF"):
		severity = "HARD"
	if severity == "OFF":
		return None
	return (
		severity,
		"WAGE_CODE_50",
		_(
			"Wage Code §2(y): Basic + DA is {0:.2f}% of total earnings ({1:.2f} of {2:.2f}), "
			"below the required {3:.2f}%. Restructure so Basic + DA ≥ {3:.2f}% of CTC."
		).format(actual_pct, basic_da, total, pct_floor),
	)


def check_pf_components_present(doc):
	"""When PF applies (Company opted in OR headcount ≥ threshold), the
	PF Employee + PF Employer rows must be present; EPS + EDLI + admin
	charges should also be present (WARN if missing)."""
	if not doc.company:
		return None
	mapping = get_mapping_for_company(doc.company)
	headcount = _company_headcount(doc.company)
	threshold = int(_hr_setting("pf_minimum_headcount_for_applicability", 20) or 20)
	# Heuristic: PF applies if headcount ≥ threshold OR mapping has PF set.
	pf_applies = headcount >= threshold or (mapping and mapping.pf_employee_component)
	if not pf_applies:
		return None

	if not mapping:
		return (
			"WARN",
			"STAT_MAPPING_MISSING",
			_(
				"PF appears to apply for {0} (headcount {1} ≥ {2}) but no Statutory "
				"Component Mapping is configured. Create one to enable detailed PF checks."
			).format(doc.company, headcount, threshold),
		)

	deductions = _component_names(doc.deductions)
	earnings = _component_names(doc.earnings)
	all_comps = deductions | earnings
	issues = []
	required = [
		(mapping.pf_employee_component, "PF Employee", "PF_EMPLOYEE_MISSING", "HARD"),
		(mapping.pf_employer_component, "PF Employer", "PF_EMPLOYER_MISSING", "HARD"),
	]
	recommended = [
		(mapping.eps_component, "EPS (employer)", "PF_EPS_MISSING", "WARN"),
		(mapping.edli_component, "EDLI (employer)", "PF_EDLI_MISSING", "WARN"),
		(mapping.pf_admin_charges_component, "PF Admin Charges", "PF_ADMIN_MISSING", "WARN"),
	]
	for comp, label, code, sev in required + recommended:
		if not comp:
			issues.append(
				(
					sev,
					code,
					_(
						"{0} component is not mapped in Statutory Component Mapping for {1}. "
						"Map it to the relevant Salary Component."
					).format(label, doc.company),
				)
			)
			continue
		if comp not in all_comps:
			issues.append(
				(
					sev,
					code,
					_(
						"Statutory Component Mapping says {0} = '{1}', but it is absent "
						"from this Salary Structure. Add the row."
					).format(label, comp),
				)
			)
	return issues or None


def check_esi_components_for_threshold(doc):
	"""If monthly gross ≤ HR Settings.esi_wage_ceiling, ESI components
	must be present."""
	monthly_gross = _earnings_total_monthly(doc)
	ceiling = flt(_hr_setting("esi_wage_ceiling", 21000))
	if monthly_gross > ceiling:
		return None  # ESI doesn't apply at this wage level
	if not doc.company:
		return None
	mapping = get_mapping_for_company(doc.company)
	if not mapping:
		return (
			"WARN",
			"ESI_MAPPING_MISSING",
			_(
				"Monthly gross {0:.2f} ≤ ESI ceiling {1:.0f} but no Statutory Component "
				"Mapping exists for {2}. Configure one to enforce ESI checks."
			).format(monthly_gross, ceiling, doc.company),
		)
	deductions = _component_names(doc.deductions)
	earnings = _component_names(doc.earnings)
	all_comps = deductions | earnings
	issues = []
	required = [
		(mapping.esi_employee_component, "ESI Employee", "ESI_EMPLOYEE_MISSING"),
		(mapping.esi_employer_component, "ESI Employer", "ESI_EMPLOYER_MISSING"),
	]
	for comp, label, code in required:
		if not comp:
			issues.append(
				(
					"HARD",
					code,
					_(
						"Monthly gross {0:.2f} ≤ ESI ceiling — {1} component is not mapped "
						"in Statutory Component Mapping for {2}."
					).format(monthly_gross, label, doc.company),
				)
			)
			continue
		if comp not in all_comps:
			issues.append(
				(
					"HARD",
					code,
					_(
						"Monthly gross {0:.2f} ≤ ESI ceiling — {1} component '{2}' is missing "
						"from this Salary Structure."
					).format(monthly_gross, label, comp),
				)
			)
	return issues or None


def check_pt_component_for_state(doc):
	"""For the state implied by this structure, if PT applies, the PT
	component must be present in deductions."""
	state = _state_from_employee_or_company(doc)
	if not state:
		return (
			"INFO",
			"PT_STATE_UNKNOWN",
			_(
				"Could not resolve an Indian State for this Salary Structure (no Assignments "
				"with state-bearing addresses; HR Settings.default_pt_state is unset). "
				"PT applicability will not be checked."
			),
		)
	state_doc = frappe.get_cached_doc("Indian State", state)
	if not state_doc.pt_applicable:
		return None  # State doesn't levy PT (e.g., Delhi, UP)
	if not doc.company:
		return None
	mapping = get_mapping_for_company(doc.company)
	deductions = _component_names(doc.deductions)
	if mapping and mapping.pt_component:
		if mapping.pt_component not in deductions:
			return (
				"HARD",
				"PT_COMPONENT_MISSING",
				_(
					"State {0} levies PT, but the mapped PT Component '{1}' is absent from "
					"this Salary Structure deductions."
				).format(state_doc.state_name, mapping.pt_component),
			)
		return None
	# No mapping but PT applies — warn (HR may use a generic PT row).
	pt_present = any(
		"professional tax" in (c or "").lower() or "pt" == (c or "").lower().strip()
		for c in deductions
	)
	if not pt_present:
		return (
			"WARN",
			"PT_COMPONENT_MISSING",
			_(
				"State {0} levies PT, but no Professional Tax component was detected in this "
				"Salary Structure. Add a PT row (and map it via Statutory Component Mapping)."
			).format(state_doc.state_name),
		)
	return None


def check_lwf_for_state(doc):
	"""Same pattern as PT — if state mandates LWF, components must exist."""
	state = _state_from_employee_or_company(doc)
	if not state:
		return None
	state_doc = frappe.get_cached_doc("Indian State", state)
	if not state_doc.lwf_applicable:
		return None
	if not doc.company:
		return None
	mapping = get_mapping_for_company(doc.company)
	deductions = _component_names(doc.deductions)
	earnings = _component_names(doc.earnings)
	all_comps = deductions | earnings
	if mapping:
		issues = []
		if mapping.lwf_employee_component and mapping.lwf_employee_component not in all_comps:
			issues.append(
				(
					"WARN",
					"LWF_EMPLOYEE_MISSING",
					_(
						"State {0} mandates LWF, but the mapped LWF Employee Component '{1}' "
						"is absent from this Salary Structure."
					).format(state_doc.state_name, mapping.lwf_employee_component),
				)
			)
		if mapping.lwf_employer_component and mapping.lwf_employer_component not in all_comps:
			issues.append(
				(
					"INFO",
					"LWF_EMPLOYER_MISSING",
					_(
						"State {0} mandates employer LWF contribution of {1:.2f}; mapped "
						"component '{2}' isn't on the structure (this is informational — "
						"employer contributions may not appear on the slip)."
					).format(
						state_doc.state_name,
						flt(state_doc.lwf_employer_amount),
						mapping.lwf_employer_component,
					),
				)
			)
		return issues or None
	# No mapping — substring fallback
	lwf_present = any("lwf" in (c or "").lower() or "labour welfare" in (c or "").lower() for c in all_comps)
	if not lwf_present:
		return (
			"INFO",
			"LWF_COMPONENT_MISSING",
			_(
				"State {0} mandates LWF (₹{1:.2f} employee + ₹{2:.2f} employer); no LWF "
				"component was detected in this Salary Structure."
			).format(
				state_doc.state_name,
				flt(state_doc.lwf_employee_amount),
				flt(state_doc.lwf_employer_amount),
			),
		)
	return None


def check_hra_component_present(doc):
	"""If HRA is implied (company has an hra_component, or structure has a
	row whose name contains 'HRA'), it should be mapped."""
	if not doc.company:
		return None
	mapping = get_mapping_for_company(doc.company)
	earnings = _component_names(doc.earnings)
	hra_row_present = any("hra" in (c or "").lower() or "house rent" in (c or "").lower() for c in earnings)
	company_hra = frappe.db.get_value("Company", doc.company, "hra_component")
	if mapping and mapping.hra_component:
		if mapping.hra_component not in earnings:
			return (
				"WARN",
				"HRA_COMPONENT_MISSING",
				_(
					"Statutory Component Mapping says HRA = '{0}', but it is absent from "
					"this Salary Structure earnings. HRA exemption (Section 10(13A)) requires "
					"the row to exist."
				).format(mapping.hra_component),
			)
		return None
	if company_hra and not hra_row_present:
		return (
			"INFO",
			"HRA_COMPONENT_MISSING",
			_(
				"Company {0} has hra_component='{1}' but no HRA row is present in this "
				"structure. Employees on this structure will not be able to claim HRA exemption."
			).format(doc.company, company_hra),
		)
	return None


def check_minimum_wage_compliance(doc):
	"""For each assigned Employee with a designation_category, compare
	the structure's monthly gross against the effective minimum wage."""
	if not int(_hr_setting("enforce_minimum_wage_validation", 1) or 0):
		return None
	monthly_gross = _earnings_total_monthly(doc)
	if not monthly_gross:
		return None

	assignments = frappe.get_all(
		"Salary Structure Assignment",
		filters={"salary_structure": doc.name, "docstatus": ("!=", 2)},
		fields=["employee"],
		limit=20,
	)
	issues = []
	checked = 0
	for a in assignments:
		emp = frappe.db.get_value(
			"Employee",
			a.employee,
			["grade", "designation", "company"],
			as_dict=True,
		)
		if not emp:
			continue
		designation_category = _resolve_designation_category(emp)
		if not designation_category:
			continue
		state = _state_for_employee(a.employee)
		if not state:
			continue
		mw = get_effective_minimum_wage(state, designation_category)
		if not mw:
			continue
		floor = derive_effective_monthly_floor(mw)
		if not floor:
			continue
		checked += 1
		if monthly_gross < floor:
			issues.append(
				(
					"HARD",
					"MIN_WAGE_VIOLATION",
					_(
						"Employee {0} ({1} / {2}): structure monthly gross {3:.2f} < notified "
						"minimum wage {4:.2f} (effective from {5}). Increase pay or change "
						"designation_category."
					).format(
						a.employee,
						state,
						designation_category,
						monthly_gross,
						floor,
						mw.effective_from,
					),
				)
			)
	return issues or None


def _resolve_designation_category(emp):
	"""Map an Employee's grade / designation to a Minimum Wage Notification
	designation_category. Reads Employee Grade.minimum_wage_category if set
	(extended via Custom Field in a future patch), else Designation
	custom_designation_category, else None."""
	if emp.get("grade"):
		cat = frappe.db.get_value("Employee Grade", emp.grade, "minimum_wage_category")
		if cat:
			return cat
	if emp.get("designation"):
		cat = frappe.db.get_value("Designation", emp.designation, "minimum_wage_category")
		if cat:
			return cat
	return None


# ---------------------------------------------------------------------------
# Assignment-level checks
# ---------------------------------------------------------------------------


def check_employee_statutory_ids_at_assignment(doc):
	"""Runs on Salary Structure Assignment.validate. PAN required; UAN
	required if PF applies; ESIC IP required if ESI applies."""
	if not doc.employee:
		return None
	emp = frappe.db.get_value(
		"Employee",
		doc.employee,
		["pan_number", "uan_number", "esic_ip_number", "company"],
		as_dict=True,
	)
	if not emp:
		return None
	issues = []
	if not emp.get("pan_number"):
		issues.append(
			(
				"HARD",
				"EMP_PAN_MISSING",
				_(
					"Employee {0} has no PAN number set. PAN is mandatory for Form 16 "
					"and TDS deductions; salary cannot be processed without it."
				).format(doc.employee),
			)
		)
	# PF applicability via company headcount or mapping
	pf_applies = False
	if emp.company:
		mapping = get_mapping_for_company(emp.company)
		headcount = _company_headcount(emp.company)
		threshold = int(_hr_setting("pf_minimum_headcount_for_applicability", 20) or 20)
		pf_applies = headcount >= threshold or (mapping and mapping.pf_employee_component)
	if pf_applies and not emp.get("uan_number"):
		issues.append(
			(
				"WARN",
				"EMP_UAN_MISSING",
				_(
					"Employee {0} has no UAN. PF appears to apply (Company headcount ≥ {1} "
					"or PF components mapped); generate / capture UAN."
				).format(doc.employee, _hr_setting("pf_minimum_headcount_for_applicability", 20)),
			)
		)
	# ESI applicability — depends on this assignment's base + variable
	from frappe.utils import flt as _flt

	base_plus_variable = _flt(doc.base or 0) + _flt(doc.variable or 0)
	esi_ceiling = _flt(_hr_setting("esi_wage_ceiling", 21000))
	if base_plus_variable and base_plus_variable <= esi_ceiling and not emp.get("esic_ip_number"):
		issues.append(
			(
				"WARN",
				"EMP_ESIC_MISSING",
				_(
					"Employee {0} earns {1:.2f} ≤ ESI ceiling {2:.0f} but has no ESIC IP "
					"number. Register and capture the IP number."
				).format(doc.employee, base_plus_variable, esi_ceiling),
			)
		)
	return issues or None


def check_income_tax_slab_assigned(doc):
	"""Assignment should have an Income Tax Slab for the current FY (WARN)."""
	if not doc.employee:
		return None
	if doc.get("income_tax_slab"):
		return None
	# Only flag for new-regime-relevant structures
	return (
		"WARN",
		"INCOME_TAX_SLAB_MISSING",
		_(
			"Employee {0} Salary Structure Assignment has no Income Tax Slab set. "
			"TDS-on-salary will not deduct correctly until an active slab is linked."
		).format(doc.employee),
	)


def check_dpdp_consent_for_aadhaar(doc):
	"""INFO — forward-looking. If Employee has full Aadhaar stored,
	prompt to capture consent. By design we store only aadhaar_last_4
	so this almost never fires; included so the framework is in place
	when DPDP Rules are notified."""
	if not int(_hr_setting("dpdp_aadhaar_consent_required", 1) or 0):
		return None
	if not doc.employee:
		return None
	# We only persist last-4 (per multi_employee_architecture). The full
	# Aadhaar number is never supposed to live in the DB. This check exists
	# as a safety net in case future imports introduce a full-aadhaar field.
	meta = frappe.get_meta("Employee")
	if meta.get_field("aadhaar_number"):
		val = frappe.db.get_value("Employee", doc.employee, "aadhaar_number")
		if val:
			return (
				"INFO",
				"DPDP_AADHAAR_CONSENT",
				_(
					"Employee {0} appears to have a full Aadhaar number stored — DPDP Rules "
					"require an explicit consent record. Capture consent or reduce to last-4."
				).format(doc.employee),
			)
	return None


# ---------------------------------------------------------------------------
# Check registries
# ---------------------------------------------------------------------------


STRUCTURE_LEVEL_CHECKS = (
	check_wage_code_50_rule,
	check_pf_components_present,
	check_esi_components_for_threshold,
	check_pt_component_for_state,
	check_lwf_for_state,
	check_hra_component_present,
	check_minimum_wage_compliance,
)


ASSIGNMENT_LEVEL_CHECKS = (
	check_employee_statutory_ids_at_assignment,
	check_income_tax_slab_assigned,
	check_dpdp_consent_for_aadhaar,
)
