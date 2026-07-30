# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Lifecycle glue for accountability (Phase 3b).

Master accountability rots without lifecycle wiring. Two hooks keep it honest:

  * LEAVER — an employee can't be relieved while still holding the bag. Rides the
    existing Employee Separation No-Dues gate: the accountability lens is the
    automatic check; a non-clear lens hard-blocks Separation submission.
  * MOVER — on a department / company change (Transfer / Promotion), surface the
    accountability that must be handed over, so HR reassigns it rather than
    letting it silently follow (or not follow) the person.
"""

import frappe
from frappe import _


def block_submit_if_accountability_pending(doc, method=None):
	"""Employee Separation before_submit: refuse while the leaver is still DRI of
	an active KRA, head of a department, or holds open Accountable task instances.

	The check is automatic (the lens returns is_clear=True when nothing is owed)
	and never blocks on a lens hiccup — it's a governance gate, not a tripwire.
	"""
	if not doc.get("employee"):
		return
	from indian_hrms_compliance.api.accountability import compute_accountability

	try:
		lens = compute_accountability(doc.employee)
	except Exception:
		# Fail CLOSED — an un-skippable governance gate must not be bypassed by a
		# transient lens error (the sibling No-Dues block fails closed too). HR
		# resolves and retries; the traceback is captured for diagnosis.
		frappe.log_error("Accountability handover check failed")
		frappe.throw(
			_("Could not verify accountability handover for this employee — resolve and retry."),
			title=_("Accountability Check Failed"),
		)
	if lens.get("is_clear"):
		return
	frappe.throw(
		_(
			"Cannot complete Separation — {0} still holds active accountability that must be "
			"handed over first:"
		).format(doc.get("employee_name") or doc.employee)
		+ "<br>"
		+ "<br>".join(lens.get("blocking_reasons") or [])
		+ "<br><br>"
		+ _("Reassign these (DRI / headship / open instances), then complete the Separation."),
		title=_("Accountability Handover Required"),
	)


def warn_mover_accountability(doc, method=None):
	"""Employee Transfer validate: when the move changes department or company,
	surface what the mover is accountable for so HR hands it over deliberately.

	A warning, not a block — a transfer isn't an exit; but the DRI roles,
	headship, and open instances should be consciously reassigned or carried.
	"""
	emp = doc.get("employee")
	if not emp:
		return
	# Only prompt when the move actually changes org placement. Key on the stable
	# `fieldname` (machine key) not the `property` label, which can be translated
	# or relabelled; fall back to `property` for older rows.
	changes = doc.get("transfer_details") or []
	moves_org = any(
		((c.get("fieldname") or c.get("property") or "").lower() in ("department", "company"))
		for c in changes
	)
	# Some Transfer flows carry new_company directly — only a REAL change counts.
	if not moves_org and doc.get("new_company") and doc.get("new_company") != doc.get("company"):
		moves_org = True
	if not moves_org:
		return
	try:
		from indian_hrms_compliance.api.accountability import compute_accountability

		lens = compute_accountability(emp)
	except Exception:
		return  # a warning, not a gate — never break a transfer save on a hiccup
	bits = []
	if lens.get("dri_kras"):
		bits.append(_("{0} active KRA(s) as DRI").format(len(lens["dri_kras"])))
	if lens.get("headed_departments"):
		bits.append(_("{0} department(s) headed").format(len(lens["headed_departments"])))
	if lens.get("owned_playbooks"):
		bits.append(_("{0} playbook(s) owned").format(len(lens["owned_playbooks"])))
	if lens.get("open_task_instances"):
		bits.append(_("{0} open task instance(s)").format(lens["open_task_instances"]))
	if lens.get("approver_of"):
		bits.append(_("approver on {0} task(s)").format(lens["approver_of"]))
	if not bits:
		return
	frappe.msgprint(
		_("Accountability handover: {0} carries {1}. Reassign or consciously carry these with the move.").format(
			lens.get("employee_name") or emp, ", ".join(bits)
		),
		title=_("Accountability to Hand Over"),
		indicator="orange",
	)
