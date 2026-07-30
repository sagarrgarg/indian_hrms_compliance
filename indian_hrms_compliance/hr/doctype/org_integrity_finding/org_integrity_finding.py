# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Org Integrity Finding + the nightly Org Integrity Check (Step 2).

Step 1 gave tasks a risk tier, every KRA/task a single accountable owner (DRI),
and an approval cycle. But Step 1 can only *warn on save* — nobody re-opens a
KRA just to notice its DRI has left, and a task instance whose approver can no
longer act sits silently in HR's backstop queue. This nightly sweep is the
active half: it re-derives those same governance conditions across the whole
org, records each as a durable, de-duplicated Finding, and escalates it once to
the person who can fix it — the DRI's reporting manager, the employee's manager,
or HR.

Design guarantees:
  * IDEMPOTENT — a recurring condition updates ONE finding (its `dedup_key`),
    never piles up duplicates; a condition that clears auto-resolves.
  * ESCALATE ONCE — the notification fires when a finding is first opened (or
    re-opened after resolving), not every night, so this is a safety net, not a
    spam cannon. The persistent finding list is the ongoing surface.
  * DEFENSIVE — each check is isolated; one failing check can't abort the sweep
    or the nightly scheduler, and every read is guarded so a not-yet-migrated
    field degrades to "skip" rather than crash.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, getdate, now_datetime, today

DOCTYPE = "Org Integrity Finding"

# check_type -> severity. Kept here so the map is one place, not sprinkled.
CHECK_SEVERITY = {
	"DRI Inactive": "High",
	"DRI Missing": "Medium",
	"Task Owner Inactive": "Medium",
	"Stranded Approval": "High",
	"Critical Unroutable": "High",
	"Critical Overdue": "High",
	"Vacant Department Head": "Medium",
}

_SYSTEM_USERS = ("Administrator", "Guest")


class OrgIntegrityFinding(Document):
	pass


# --------------------------------------------------------------------------- #
# Config (HR Settings) — read defensively; a Single's field may not exist yet.
# --------------------------------------------------------------------------- #
def _setting(fieldname: str, default):
	if not frappe.get_meta("HR Settings").has_field(fieldname):
		return default
	val = frappe.db.get_single_value("HR Settings", fieldname)
	return default if val in (None, "") else val


def _escalation_role() -> str:
	return _setting("org_integrity_escalation_role", "HR Manager") or "HR Manager"


# --------------------------------------------------------------------------- #
# Escalation target resolution
# --------------------------------------------------------------------------- #
def _manager_user(reports_to: str | None) -> str | None:
	"""The reporting manager's User — only if it's a real, ENABLED login.

	A disabled manager account is a black hole: notifying it stamps the finding
	as escalated while nobody ever sees it. Returning None here lets the caller
	fall through to HR, which is exactly the "manager also left in the reorg"
	case where DRI-Inactive matters most.
	"""
	if not reports_to:
		return None
	user = frappe.db.get_value("Employee", reports_to, "user_id")
	if not user or user in _SYSTEM_USERS:
		return None
	if not frappe.db.get_value("User", user, "enabled"):
		return None
	return user


def _company_hr_users(company: str | None) -> list[str]:
	"""Enabled holders of the escalation role who can see this company.

	Reuses Step 1's `_hr_company_scope`: an HR user with no Company User
	Permission sees everything (scope None); one restricted to some companies
	only escalates for those. Keeps HR-targeted findings from leaking a
	sibling company's governance state to the wrong HR desk.

	When the finding has NO company (a Goal need not carry one), scope-filtering
	would drop every company-restricted HR user and could reach nobody — so an
	un-companied finding goes to ALL enabled escalation-role holders rather than
	silently un-escalating.
	"""
	from indian_hrms_compliance.api import _hr_company_scope

	holders = frappe.get_all(
		"Has Role",
		filters={"role": _escalation_role(), "parenttype": "User"},
		pluck="parent",
	)
	if not holders:
		return []
	enabled = set(
		frappe.get_all("User", filters={"name": ("in", holders), "enabled": 1}, pluck="name")
	)
	out = []
	for u in holders:
		if u not in enabled or u in _SYSTEM_USERS:
			continue
		if not company:
			out.append(u)  # can't scope an un-companied finding — tell all HR
			continue
		scope = _hr_company_scope(u)
		if scope is None or company in scope:
			out.append(u)
	return out


def _targets(finding: dict, severity: str) -> list[str]:
	"""Who to notify for a finding.

	The named manager (DRI's / employee's) gets the direct nudge — they own the
	fix. HR is added too whenever the finding is HIGH severity, or whenever there
	is no reachable manager, so the governance owner is never left out and a
	departed-manager case still lands somewhere real. De-duplicated, order kept.
	"""
	from indian_hrms_compliance.api import _dedupe_users

	targets: list[str] = []
	manager = finding.get("escalate_to")
	if manager and manager not in _SYSTEM_USERS:
		targets.append(manager)
	if not targets or severity == "High":
		targets.extend(_company_hr_users(finding.get("company")))
	return _dedupe_users(targets, set())


# --------------------------------------------------------------------------- #
# The checks — each returns a list of finding dicts. Pure reads, no writes.
# --------------------------------------------------------------------------- #
def _check_dri_inactive() -> list[dict]:
	"""An Active KRA whose named DRI is no longer an active employee.

	THE Step-1 promise (kra.py `_warn_if_dri_inactive` only warns on save):
	escalate to the departed DRI's reporting manager, who owns finding a
	replacement, falling back to HR.
	"""
	# LEFT JOIN so a DRI whose Employee record was hard-deleted (a dangling link,
	# not just an inactive one) is caught too — an INNER JOIN would silently drop
	# it, and `_check_dri_missing` won't catch it either (the link is non-empty).
	# Acting cover is pulled so a departed DRI who HAS valid cover is not flagged.
	acting_cols = ""
	if frappe.get_meta("KRA").has_field("acting_dri"):
		acting_cols = ", k.acting_dri, k.acting_until"
	rows = frappe.db.sql(
		f"""
		SELECT k.name, k.title, k.company, k.dri,
		       e.name AS emp, e.employee_name, e.reports_to, e.status AS emp_status{acting_cols}
		FROM `tabKRA` k
		LEFT JOIN `tabEmployee` e ON e.name = k.dri
		WHERE k.status = 'Active' AND k.dri IS NOT NULL AND k.dri != ''
		  AND (e.name IS NULL OR e.status != 'Active')
		""",
		as_dict=True,
	)
	from indian_hrms_compliance.hr.doctype.kra.kra import effective_dri

	out = []
	for r in rows:
		# A valid Acting DRI means the KRA is covered, not orphaned. But cover only
		# counts if the ACTING person is themselves still active — otherwise a KRA
		# whose DRI AND acting stand-in have both departed would be invisible to
		# the one check meant to catch orphaned accountability. (Expired cover
		# already falls back to the dead DRI via effective_dri, so it's flagged.)
		holder = effective_dri(r)
		if holder != r.dri and frappe.db.get_value("Employee", holder, "status") == "Active":
			continue
		state = r.emp_status if r.emp else _("deleted")
		out.append(
			{
				"check_type": "DRI Inactive",
				"company": r.company,
				"reference_doctype": "KRA",
				"reference_name": r.name,
				"subject_label": r.title or r.name,
				"detail": _(
					"The DRI {0} ({1}) for KRA '{2}' is no longer an active employee "
					"({3}). Reassign the KRA to a current owner."
				).format(r.employee_name or r.dri, r.dri, r.title or r.name, state),
				# A deleted DRI has no reports_to to read, so this correctly falls
				# through to HR via _targets.
				"escalate_to": _manager_user(r.reports_to),
			}
		)
	return out


def _check_dri_missing() -> list[dict]:
	"""An Active KRA with no DRI at all (legacy rows that only warn on save)."""
	rows = frappe.db.sql(
		"""
		SELECT name, title, company FROM `tabKRA`
		WHERE status = 'Active' AND (dri IS NULL OR dri = '')
		""",
		as_dict=True,
	)
	return [
		{
			"check_type": "DRI Missing",
			"company": r.company,
			"reference_doctype": "KRA",
			"reference_name": r.name,
			"subject_label": r.title or r.name,
			"detail": _(
				"Active KRA '{0}' has no DRI — no single person is accountable for it. "
				"Name one."
			).format(r.title or r.name),
			"escalate_to": None,
		}
		for r in rows
	]


def _check_task_owner_inactive() -> list[dict]:
	"""An Active HRMS Task whose DRI (task_owner, a User) is a disabled account."""
	rows = frappe.db.sql(
		"""
		SELECT t.name, t.task_name, t.company, t.task_owner
		FROM `tabHRMS Task` t
		JOIN `tabUser` u ON u.name = t.task_owner
		WHERE t.status = 'Active'
		  AND t.task_owner NOT IN ('Administrator', 'Guest')
		  AND u.enabled = 0
		""",
		as_dict=True,
	)
	return [
		{
			"check_type": "Task Owner Inactive",
			"company": r.company,
			"reference_doctype": "HRMS Task",
			"reference_name": r.name,
			"subject_label": r.task_name or r.name,
			"detail": _(
				"The owner (DRI) {0} of Active task '{1}' is a disabled user account. "
				"Reassign the task."
			).format(r.task_owner, r.task_name or r.name),
			"escalate_to": None,
		}
		for r in rows
	]


def _check_stranded_approvals() -> list[dict]:
	"""A task instance submitted for approval but with no one able to approve it.

	Reuses Step 1's `_task_routed_approvers`: an empty result means the routed
	approver is the doer / disabled / an empty role — the segregation-of-duties
	gate would refuse everyone. Only flags instances that have been stuck beyond
	the configured SLA, so a same-day submission awaiting its manager is not
	noise.
	"""
	meta = frappe.get_meta("Goal")
	if not meta.has_field("submitted_at"):
		return None  # not migrated yet — "did not run", do NOT auto-resolve this type
	from indian_hrms_compliance.api import _task_routed_approvers

	sla = int(_setting("org_integrity_stranded_sla_days", 3))
	cutoff = add_to_date(now_datetime(), days=-sla)

	# Only fields the doctype actually has — every one the approver-resolution
	# helper reads is requested when present so a partially-migrated Goal
	# degrades to a false-negative (skip) rather than a KeyError.
	fields = ["name", "goal_name", "company", "employee", "employee_name"]
	for f in ("submitted_at", "submitted_by", "approver_user", "approver_role", "performed_by"):
		if meta.has_field(f):
			fields.append(f)

	rows = frappe.get_all(
		"Goal",
		filters={
			"goal_type": "Task Instance",
			"status": "In Progress",
			"submitted_at": ("<", cutoff),
		},
		fields=fields,
	)
	out = []
	for g in rows:
		if _task_routed_approvers(g):
			continue  # someone CAN act — not stranded
		# Goal.company can be blank; fall back to the employee's company so the
		# finding is company-scoped and reaches the right HR desk.
		company = g.company or frappe.db.get_value("Employee", g.employee, "company")
		out.append(
			{
				"check_type": "Stranded Approval",
				"company": company,
				"reference_doctype": "Goal",
				"reference_name": g.name,
				"subject_label": g.goal_name or g.name,
				"detail": _(
					"Task '{0}' from {1} has been awaiting approval since {2} with no one "
					"able to approve it (the routed approver is the doer, disabled, or an "
					"empty role). Re-route or approve it."
				).format(
					g.goal_name or g.name, g.employee_name or g.employee, getdate(g.submitted_at)
				),
				"escalate_to": None,
			}
		)
	return out


def _check_critical_unroutable() -> list[dict]:
	"""An Active Critical task whose approver routing can resolve to nobody.

	Only the statically-decidable cases: a Specific User route with no user, or
	a Specific Role route whose role has no enabled holder. 'Reports To' is
	per-employee and can't be judged from the template, so it's out of scope
	here (a Reports-To instance with no manager surfaces as Stranded Approval).
	"""
	if not frappe.get_meta("HRMS Task").has_field("risk_tier"):
		return None  # not migrated yet — "did not run"
	rows = frappe.get_all(
		"HRMS Task",
		filters={"status": "Active", "risk_tier": "Critical", "requires_approval": 1},
		fields=["name", "task_name", "company", "approver_resolution", "approver_user", "approver_role"],
	)
	out = []
	for t in rows:
		reason = None
		if t.approver_resolution == "Specific User" and not t.approver_user:
			reason = _("its approver resolution is 'Specific User' but no user is set")
		elif t.approver_resolution == "Specific Role":
			if not t.approver_role:
				reason = _("its approver resolution is 'Specific Role' but no role is set")
			else:
				holders = frappe.get_all(
					"Has Role",
					filters={"role": t.approver_role, "parenttype": "User"},
					pluck="parent",
				)
				enabled = frappe.get_all(
					"User",
					filters={"name": ("in", holders or [""]), "enabled": 1},
					pluck="name",
				)
				# Match Step 1's routing contract exactly: `_dedupe_users` keeps
				# Administrator as a valid approver (task_owner defaults to
				# __user) and drops only Guest. Excluding Administrator here would
				# flag a task that actually routes fine as "unroutable".
				live = [u for u in enabled if u != "Guest"]
				if not live:
					reason = _("no active user holds its approver role '{0}'").format(t.approver_role)
		if not reason:
			continue
		out.append(
			{
				"check_type": "Critical Unroutable",
				"company": t.company,
				"reference_doctype": "HRMS Task",
				"reference_name": t.name,
				"subject_label": t.task_name or t.name,
				"detail": _(
					"Critical task '{0}' requires approval but {1}. Every instance it "
					"creates will land unapprovable. Fix its approver routing."
				).format(t.task_name or t.name, reason),
				"escalate_to": None,
			}
		)
	return out


def _check_critical_overdue() -> list[dict]:
	"""A Critical task instance overdue beyond the SLA — escalate to the manager."""
	# risk_tier lives on HRMS Task; task_template / goal_type / due_date are the
	# task-instance columns a DIFFERENT Step-1 patch adds to Goal. Guard BOTH, so
	# a half-migrated site skips rather than erroring on an unknown column.
	if not frappe.get_meta("HRMS Task").has_field("risk_tier"):
		return None  # not migrated yet — "did not run"
	if not frappe.get_meta("Goal").has_field("task_template"):
		return None
	sla = int(_setting("org_integrity_overdue_sla_days", 7))
	cutoff = getdate(add_to_date(today(), days=-sla))
	rows = frappe.db.sql(
		"""
		SELECT g.name, g.goal_name, COALESCE(NULLIF(g.company, ''), e.company) AS company,
		       g.employee, g.due_date, e.employee_name, e.reports_to
		FROM `tabGoal` g
		JOIN `tabHRMS Task` t ON t.name = g.task_template
		JOIN `tabEmployee` e ON e.name = g.employee
		WHERE g.goal_type = 'Task Instance'
		  AND g.status IN ('Pending', 'In Progress')
		  AND t.risk_tier = 'Critical'
		  AND g.due_date < %s
		""",
		(cutoff,),
		as_dict=True,
	)
	return [
		{
			"check_type": "Critical Overdue",
			"company": r.company,
			"reference_doctype": "Goal",
			"reference_name": r.name,
			"subject_label": r.goal_name or r.name,
			"detail": _(
				"Critical task '{0}' for {1} was due on {2} and is still not done. "
				"Escalated for action."
			).format(r.goal_name or r.name, r.employee_name or r.employee, r.due_date),
			"escalate_to": _manager_user(r.reports_to),
		}
		for r in rows
	]


# (check fn, the check_type it owns). The type is declared, not inferred, so a
# check that legitimately finds nothing this run is still known to have COVERED
# its type — which is what lets auto-resolve safely close its cleared findings
# without ever touching the findings of a check that failed or was skipped.
def _check_vacant_department_head() -> list[dict] | None:
	"""A department whose head cannot be resolved — no head, or a head/acting who
	has left — so 'assign to head', escalations and the reporting tree have no
	anchor. Only meaningful once the head field exists.
	"""
	if not frappe.get_meta("Department").has_field("department_head"):
		return None
	from indian_hrms_compliance.overrides.org_tree import department_head_of

	out = []
	for d in frappe.get_all(
		"Department",
		filters={"disabled": 0, "is_group": 0},
		fields=["name", "department_name", "company", "department_head"],
	):
		if department_head_of(d.name):
			continue  # a live head (or acting) resolves — fine
		# Only flag departments that actually have people to head; an empty
		# placeholder department needing no head is not a governance problem.
		if not frappe.db.count("Employee", {"department": d.name, "status": "Active"}):
			continue
		stale = d.department_head  # set but not resolvable (departed) vs never set
		out.append(
			{
				"check_type": "Vacant Department Head",
				"company": d.company,
				"reference_doctype": "Department",
				"reference_name": d.name,
				"subject_label": d.department_name or d.name,
				"detail": _(
					"Department '{0}' has active staff but no resolvable head ({1}). "
					"Assign a Department Head so its reporting lines and escalations have an anchor."
				).format(
					d.department_name or d.name,
					_("the named head is no longer active") if stale else _("none named"),
				),
				"escalate_to": None,
			}
		)
	return out


_CHECKS = (
	(_check_dri_inactive, "DRI Inactive"),
	(_check_vacant_department_head, "Vacant Department Head"),
	(_check_dri_missing, "DRI Missing"),
	(_check_task_owner_inactive, "Task Owner Inactive"),
	(_check_stranded_approvals, "Stranded Approval"),
	(_check_critical_unroutable, "Critical Unroutable"),
	(_check_critical_overdue, "Critical Overdue"),
)


# --------------------------------------------------------------------------- #
# Upsert + escalate + auto-resolve
# --------------------------------------------------------------------------- #
def _dedup_key(f: dict) -> str:
	return f"{f['check_type']}::{f.get('reference_doctype') or ''}::{f.get('reference_name') or ''}"


def _upsert_finding(f: dict) -> str:
	"""Create or refresh one finding. Escalates only on first open / re-open.

	Returns the dedup_key so the caller can track which conditions are still
	live this run (everything else auto-resolves)."""
	key = _dedup_key(f)
	severity = CHECK_SEVERITY.get(f["check_type"], "Medium")
	name = frappe.db.get_value(DOCTYPE, {"dedup_key": key})

	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		reopened = doc.status == "Resolved"
		doc.status = "Open"
		doc.severity = severity
		doc.company = f.get("company")
		doc.subject_label = f.get("subject_label")
		doc.detail = f.get("detail")
		doc.last_seen = now_datetime()
		if reopened:
			doc.resolved_on = None
		doc.save(ignore_permissions=True)
		if reopened:
			_escalate(doc, f)  # the condition came back — nudge again
		return key

	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"dedup_key": key,
			"check_type": f["check_type"],
			"severity": severity,
			"status": "Open",
			"company": f.get("company"),
			"reference_doctype": f.get("reference_doctype"),
			"reference_name": f.get("reference_name"),
			"subject_label": f.get("subject_label"),
			"detail": f.get("detail"),
			"first_detected": now_datetime(),
			"last_seen": now_datetime(),
		}
	)
	doc.insert(ignore_permissions=True)
	_escalate(doc, f)
	return key


def _escalate(doc, f: dict) -> None:
	"""Notify the responsible party once, and record who + when on the finding."""
	from indian_hrms_compliance.hr.doctype.hrms_task.hrms_task import _safe_pwa_notification

	targets = _targets(f, doc.severity)
	if not targets:
		return
	message = _("Governance issue ({0}): {1}").format(doc.severity, doc.detail)
	for user in targets:
		_safe_pwa_notification(
			to_user=user,
			message=message,
			ref_type=DOCTYPE,
			ref_name=doc.name,
		)
	# Record the primary recipient so the finding shows who was told, and so a
	# re-open re-stamps it. update_modified stays off — this is bookkeeping.
	frappe.db.set_value(
		DOCTYPE,
		doc.name,
		{"escalated_to": targets[0], "escalated_on": now_datetime()},
		update_modified=False,
	)


def _auto_resolve_stale(seen_keys: set, covered_types: set) -> int:
	"""Close Open findings whose condition cleared — but ONLY for check types
	that actually ran this sweep.

	Crucial safety rule: a check that raised or degraded-to-skip contributes no
	keys, so resolving "everything not seen" would false-resolve its still-valid
	findings and then re-escalate them next run. So we resolve a finding only
	when its OWN check_type is in `covered_types` (the check ran to completion)
	AND its key wasn't observed. A skipped check's findings are left untouched.
	"""
	if not covered_types:
		return 0
	open_findings = frappe.get_all(
		DOCTYPE,
		filters={"status": "Open", "check_type": ("in", list(covered_types))},
		fields=["name", "dedup_key"],
	)
	resolved = 0
	for row in open_findings:
		if row.dedup_key in seen_keys:
			continue
		frappe.db.set_value(
			DOCTYPE,
			row.name,
			{"status": "Resolved", "resolved_on": now_datetime()},
			update_modified=False,
		)
		resolved += 1
	return resolved


# --------------------------------------------------------------------------- #
# Scheduler entry point
# --------------------------------------------------------------------------- #
def run_org_integrity_check() -> dict:
	"""Scheduler (daily): the whole sweep. Idempotent + self-contained.

	Returns a small summary dict (also handy when run ad-hoc from the console).
	"""
	if not frappe.db.table_exists(DOCTYPE):
		return {"skipped": "doctype missing"}
	if not int(_setting("enable_org_integrity_check", 1) or 0):
		return {"skipped": "disabled"}

	seen_keys: set = set()
	covered_types: set = set()
	for check, check_type in _CHECKS:
		try:
			findings = check()
		except Exception:
			frappe.log_error(title=f"Org integrity check failed: {check.__name__}")
			continue
		# A check returns None to say "I could not run" (a meta-guard skipped it on
		# a not-yet-migrated site) vs [] for "I ran and found nothing". Only a
		# check that actually RAN may auto-resolve its type — otherwise a field
		# that transiently disappears would resolve, then re-escalate, real findings.
		if findings is None:
			continue
		covered_types.add(check_type)
		for f in findings:
			# Record the condition as seen BEFORE the upsert, so a transient
			# upsert failure (e.g. a concurrent run's unique-key race) can't drop
			# the key and make auto-resolve close the very finding it represents.
			seen_keys.add(_dedup_key(f))
			try:
				_upsert_finding(f)
			except Exception:
				frappe.log_error(title="Org integrity finding upsert failed")

	resolved = _auto_resolve_stale(seen_keys, covered_types)
	frappe.db.commit()
	return {"open": len(seen_keys), "covered": len(covered_types), "auto_resolved": resolved}
