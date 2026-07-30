"""Derive `risk_tier` for HRMS Tasks created before the field existed.

Step 1 of the governance mutation gives every task a risk tier so ceremony can
be proportional to risk (Routine = one tap, Standard = evidence, Critical =
evidence + approval by someone other than the doer).

The tier is derived from what each task ALREADY says about itself:
    requires_approval           -> Critical
    evidence on completion      -> Standard
    otherwise                   -> Routine

Self-contained (creates nothing it can't verify), defensive (bails when the
doctype/field is absent mid-migrate) and idempotent (blank tiers only, so a
re-run — or the twin after_migrate hook — can never overwrite a human choice).
"""

import frappe


def execute():
	if not frappe.db.table_exists("HRMS Task"):
		return

	# post_model_sync patches run BEFORE the after_migrate hooks, and risk_tier
	# is a standard field on our own doctype, so a fresh site may not have synced
	# it yet. Force the doctype through if so, then re-check rather than assume.
	if not frappe.get_meta("HRMS Task").has_field("risk_tier"):
		frappe.reload_doc("hr", "doctype", "hrms_task")
		frappe.clear_cache(doctype="HRMS Task")
	if not frappe.get_meta("HRMS Task").has_field("risk_tier"):
		return

	from indian_hrms_compliance.hr.doctype.hrms_task.hrms_task import reconcile_risk_tiers

	# Same posture as the after_migrate twin (setup.reconcile_hrms_task_risk_tiers):
	# a cosmetic, self-healing backfill must never be the thing that aborts a
	# migrate. Whichever entry point runs first, the other still converges later.
	try:
		repaired = reconcile_risk_tiers()
	except Exception:
		# Discard any partial writes rather than leaving them for the patch
		# runner to commit. Safe to drop: the backfill is blank-only and
		# idempotent, so the next migrate (or the after_migrate twin) converges.
		frappe.db.rollback()
		frappe.log_error("HRMS Task risk tier backfill failed")
		return
	if repaired:
		print(f"  Derived risk_tier for {repaired} HRMS Task(s)")
