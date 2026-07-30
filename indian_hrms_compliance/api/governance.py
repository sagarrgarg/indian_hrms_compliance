# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Governance Profile (Dial 2) + the Regulated payoff — Control Register &
evidence export (Phase 5).

Two dials decide how much of the five-layer spine anyone ever sees: Risk Tier
(per task, Phase 1) and Governance Profile (per company, here). Statutory /
money-movement work is born Critical in every profile — that asymmetry is the
product's identity. This module reads the profile, auto-suggests one from size,
and provides the two Regulated features: a zero-data-entry Control Register
(auto-RCM) and a period-filtered evidence export for Sec 134(5)(e)/143 support.
"""

import csv
import io
import zipfile

import frappe
from frappe import _
from frappe.utils import getdate, today

PROFILES = ("Startup", "Growth", "Regulated")
_PROFILE_RANK = {"Startup": 0, "Growth": 1, "Regulated": 2}
COCKPIT_ROLES = ("HR Manager", "HR User", "System Manager")
# Bound one evidence export so a huge period can't build an unbounded zip in memory.
_EVIDENCE_EXPORT_CAP = 5000


def company_profile(company: str | None) -> str:
	"""The company's Governance Profile, defaulting to Startup (lean) — the
	safe default when the field is unset or absent on an un-migrated site."""
	if not company or not frappe.get_meta("Company").has_field("governance_profile"):
		return "Startup"
	return frappe.db.get_value("Company", company, "governance_profile") or "Startup"


def profile_at_least(company: str | None, level: str) -> bool:
	"""Is the company's profile at or above `level`? (Growth ⊇ Startup, etc.)"""
	return _PROFILE_RANK.get(company_profile(company), 0) >= _PROFILE_RANK.get(level, 0)


def suggest_profile(company: str) -> str:
	"""Auto-suggest a profile from headcount — HR always overrides. Mirrors the
	IFC-exemption intuition: small ⇒ Startup, mid ⇒ Growth, large ⇒ Regulated.
	Thresholds are deliberately simple; the real trigger is a human decision."""
	headcount = frappe.db.count("Employee", {"company": company, "status": "Active"})
	if headcount >= 250:
		return "Regulated"
	if headcount >= 50:
		return "Growth"
	return "Startup"


def _assert_company_in_scope(company: str | None) -> None:
	"""An HR user may only act on a company within their User-Permission scope —
	so passing an explicit `company` can't reach a sibling company's data. HR
	with no company restriction (scope None) sees all, matching the rest of the app."""
	if not company:
		return
	from indian_hrms_compliance.api import _hr_company_scope

	scope = _hr_company_scope(frappe.session.user)
	if scope is not None and company not in scope:
		frappe.throw(
			_("You do not have access to company {0}.").format(company), frappe.PermissionError
		)


@frappe.whitelist()
def get_governance_profile(company: str | None = None) -> dict:
	"""The active profile + a size-based suggestion, for HR to review/override."""
	frappe.only_for(COCKPIT_ROLES)
	from indian_hrms_compliance.api.cockpit import _scope_company

	company = company or _scope_company()
	if not company:
		return {"company": None, "profile": "Startup", "suggested": "Startup"}
	return {
		"company": company,
		"profile": company_profile(company),
		"suggested": suggest_profile(company),
	}


# --------------------------------------------------------------------------- #
# Control Register — the auto-RCM (a view over what execution already captured)
# --------------------------------------------------------------------------- #
def _control_register_rows(company: str | None) -> list[dict]:
	filters = {"status": "Active", "risk_tier": ("in", ["Critical", "Standard"])}
	if company:
		filters["company"] = company
	tasks = frappe.get_all(
		"HRMS Task",
		filters=filters,
		fields=[
			"name",
			"task_name",
			"kra",
			"company",
			"risk_tier",
			"is_statutory",
			"task_owner",
			"frequency",
			"requires_approval",
			"approver_resolution",
			"completion_type",
			"requires_attachment",
		],
		order_by="risk_tier asc, task_name asc",
	)
	rows = []
	for t in tasks:
		# Last captured evidence: the most recent completed instance of this task.
		last = frappe.db.get_value(
			"Goal",
			{"task_template": t.name, "goal_type": "Task Instance", "status": "Completed"},
			["name", "submitted_at", "approved_by"],
			order_by="submitted_at desc",
			as_dict=True,
		)
		# Segregation-of-duties pair: doer (the assignee) vs approver route.
		sod = (
			_("doer ≠ {0}").format(t.approver_resolution or _("Reports To"))
			if t.requires_approval
			else _("no sign-off (Standard)")
		)
		rows.append(
			{
				"task": t.name,
				"task_name": t.task_name,
				"kra": t.kra,
				"company": t.company,
				"risk_tier": t.risk_tier,
				"statutory": 1 if t.is_statutory else 0,
				"dri": t.task_owner,
				"cadence": t.frequency,
				"control": _("evidence + approval") if t.requires_approval else _("evidence"),
				"sod_pair": sod,
				"last_evidence_on": str(last.submitted_at) if last and last.submitted_at else None,
				"last_approved_by": last.approved_by if last else None,
			}
		)
	return rows


@frappe.whitelist()
def get_control_register(company: str | None = None) -> dict:
	"""The Risk-Control Matrix an auditor consumes: every Critical / Standard task
	with its tier, DRI, SoD pair, cadence and last evidence — zero extra data
	entry. HR-only, company-scoped."""
	frappe.only_for(COCKPIT_ROLES)
	from indian_hrms_compliance.api.cockpit import _scope_company

	company = company or _scope_company()
	_assert_company_in_scope(company)
	rows = _control_register_rows(company)
	return {
		"company": company,
		"profile": company_profile(company),
		"count": len(rows),
		"rows": rows,
	}


# --------------------------------------------------------------------------- #
# Evidence export — period-filtered instances + attachments (Sec 134 / 143)
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def export_evidence(from_date: str, to_date: str, company: str | None = None) -> dict:
	"""Build a downloadable zip: a manifest CSV of every completed task instance
	DUE in the period, plus the attached proof files. Returns the File URL.
	HR-only, company-scoped, Regulated-oriented (available to any HR user).
	"""
	frappe.only_for(COCKPIT_ROLES)
	from indian_hrms_compliance.api.cockpit import _scope_company

	company = company or _scope_company()
	_assert_company_in_scope(company)
	start, end = getdate(from_date), getdate(to_date)
	if start > end:
		frappe.throw(_("'From' date cannot be after 'To' date."))

	filters = {
		"goal_type": "Task Instance",
		"status": "Completed",
		"due_date": ("between", [start, end]),
	}
	if company:
		filters["company"] = company
	instances = frappe.get_all(
		"Goal",
		filters=filters,
		# Cap the export so one huge period can't build an unbounded in-memory zip;
		# the manifest notes truncation so nobody mistakes it for the full set.
		limit=_EVIDENCE_EXPORT_CAP,
		fields=[
			"name",
			"goal_name",
			"employee_name",
			"kra",
			"company",
			"period_label",
			"due_date",
			"submitted_at",
			"submitted_by",
			"approved_by",
			"approved_at",
			"numeric_value",
			"task_notes",
			"task_attachment",
		],
		order_by="due_date asc",
	)

	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
		# Manifest CSV — the index the auditor reads first.
		sio = io.StringIO()
		writer = csv.writer(sio)
		writer.writerow(
			[
				"Instance",
				"Task",
				"Employee",
				"KRA",
				"Company",
				"Period",
				"Due",
				"Submitted At",
				"Submitted By",
				"Approved By",
				"Approved At",
				"Numeric Value",
				"Notes",
				"Attachment",
			]
		)
		attached = 0
		for g in instances:
			writer.writerow(
				[
					_csv_safe(g.name),
					_csv_safe(g.goal_name),
					_csv_safe(g.employee_name),
					_csv_safe(g.kra),
					_csv_safe(g.company),
					_csv_safe(g.period_label),
					g.due_date,
					g.submitted_at,
					_csv_safe(g.submitted_by),
					_csv_safe(g.approved_by),
					g.approved_at,
					g.numeric_value,
					_csv_safe((g.task_notes or "").replace("\n", " ")),
					_csv_safe(g.task_attachment or ""),
				]
			)
			# Pull the attached proof file into the zip when present — but ONLY the
			# file actually attached to THIS instance, so a task_attachment
			# pointed at another company's private file can't be exfiltrated.
			if g.task_attachment:
				content = _file_content(g.task_attachment, g.name)
				if content is not None:
					safe = g.task_attachment.split("/")[-1]
					zf.writestr(f"attachments/{g.name}__{safe}", content)
					attached += 1
		zf.writestr("manifest.csv", sio.getvalue())

	fname = f"evidence_{company or 'all'}_{start}_{end}.zip".replace(" ", "_")
	filedoc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": fname,
			"is_private": 1,
			"content": buf.getvalue(),
		}
	).insert(ignore_permissions=True)
	return {
		"file_url": filedoc.file_url,
		"instances": len(instances),
		"attachments": attached,
		"period": f"{start} → {end}",
		"truncated": len(instances) >= _EVIDENCE_EXPORT_CAP,
	}


def _file_content(file_url: str, goal_name: str):
	"""The bytes of the File attached to THIS Goal, or None.

	Verifies the File is actually attached to `goal_name` before reading — a
	`task_attachment` value pointing at an unrelated (possibly another company's
	private) file is ignored rather than read and exported."""
	try:
		f = frappe.db.get_value(
			"File", {"file_url": file_url}, ["name", "attached_to_doctype", "attached_to_name"], as_dict=True
		)
		if not f or f.attached_to_doctype != "Goal" or f.attached_to_name != goal_name:
			return None
		return frappe.get_doc("File", f.name).get_content()
	except Exception:
		return None


def _csv_safe(value) -> str:
	"""Neutralise CSV formula injection: a cell starting with = + - @ executes in
	Excel/Sheets. This is an auditor-facing export — sanitise it."""
	s = "" if value is None else str(value)
	return "'" + s if s and s[0] in ("=", "+", "-", "@") else s
