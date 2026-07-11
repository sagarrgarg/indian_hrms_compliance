# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import re

import frappe
from frappe import _
from frappe.model.naming import make_autoname, set_name_by_naming_series
from frappe.utils import add_years, cint, get_link_to_form, getdate

from erpnext.setup.doctype.employee.employee import Employee

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
UAN_RE = re.compile(r"^[0-9]{12}$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
AADHAAR_LAST4_RE = re.compile(r"^[0-9]{4}$")
AADHAAR_FULL_RE = re.compile(r"^[2-9][0-9]{11}$")  # UIDAI: 12 digits, first digit 2-9


# Verhoeff lookup tables — used by UIDAI as the Aadhaar checksum algorithm.
# Pulled from the Verhoeff paper; not project-specific.
_VERHOEFF_D = (
	(0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
	(1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
	(2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
	(3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
	(4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
	(5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
	(6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
	(7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
	(8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
	(9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
	(0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
	(1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
	(5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
	(8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
	(9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
	(4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
	(2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
	(7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def verhoeff_check_aadhaar(num: str) -> bool:
	"""UIDAI Aadhaar checksum verification (Verhoeff algorithm).
	Returns True if the supplied 12-digit string is internally consistent.
	Does NOT verify that the number was actually issued — only that it's
	mathematically possible. Useful to catch typos before storing PII.
	"""
	if not num or len(num) != 12 or not num.isdigit():
		return False
	c = 0
	for i, n in enumerate(reversed(num)):
		c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(n)]]
	return c == 0


def mask_aadhaar(num: str) -> str:
	"""Return a display-safe rendering: 'XXXX XXXX 1234'."""
	if not num or len(num) != 12 or not num.isdigit():
		return num or ""
	return f"XXXX XXXX {num[-4:]}"


def _employee_link(name):
	# Relative URL — portable across host/port without depending on site_config host_name.
	return f'<a href="/app/employee/{name}">{name}</a>'

# Fields that must match across Employee records sharing the same user_id
# (they describe the human, not the employment).
PERSON_LEVEL_FIELDS = (
	"pan_number",
	"uan_number",
	"esic_ip_number",
	"aadhaar_number",
	"aadhaar_last_4",
	"nps_pran",
	"date_of_birth",
	"gender",
)


def resolve_employee_approver(value):
	"""Resolve an Employee-typed approver field value to its linked ``user_id``.

	Employee.{leave,expense,shift_request}_approver now store an Employee, but the
	downstream approval engine (Leave Application / Expense Claim / Shift Request)
	and role/sharing/notification machinery all run on User. Use this at every
	boundary that feeds those.

	- Falsy values pass through unchanged.
	- An Employee resolves to its linked ``user_id``; an Employee with no linked
	  User resolves to ``None`` (never the Employee name, which would be an invalid
	  value for a User field).
	- A value that is already a User (e.g. a Department Approver row) passes through.
	"""
	if not value:
		return value
	if frappe.db.exists("Employee", value):
		return frappe.db.get_value("Employee", value, "user_id") or None
	return value


def employee_id_series_for_company(company: str) -> str | None:
	"""Per-company Employee ID series derived from the Company's abbreviation.

	Company abbr 'GGIL' -> series 'GGIL-.###', which make_autoname expands to
	GGIL-001, GGIL-002, ... The numeric counter is stored PER prefix in
	tabSeries, so every company numbers its own people independently
	(GGIL-001, KGOPL-001, GGIL-002). Returns None when the company has no
	usable abbreviation, so the caller can fall back to the HR Settings method.
	"""
	if not company:
		return None
	abbr = frappe.db.get_value("Company", company, "abbr")
	# Keep the prefix tidy and stable as a tabSeries key: alphanumerics only,
	# upper-cased (so 'ggil' and 'GGIL' never split into two counters).
	abbr = re.sub(r"[^A-Za-z0-9]", "", (abbr or "")).upper()
	if not abbr:
		return None
	return f"{abbr}-.###"


class EmployeeMaster(Employee):
	def autoname(self):
		series = employee_id_series_for_company(self.company)
		if series:
			# Company-abbreviation Employee IDs — e.g. GGIL-001, KGOPL-001,
			# GGIL-002. The counter is kept per prefix in tabSeries, so each
			# company numbers its people independently.
			self.name = make_autoname(series, doc=self)
			# tabSeries can lag behind the real IDs — legacy employees bulk-imported
			# with explicit names (e.g. GGIL-001..GGIL-050) never advance it — so
			# make_autoname can hand back an ID that already exists. Keep drawing the
			# next number (each call advances the counter) until one is free, so the
			# series self-heals past already-used IDs instead of failing the insert.
			while frappe.db.exists("Employee", self.name):
				self.name = make_autoname(series, doc=self)
		else:
			# No company abbreviation to key off — honour the HR Settings method.
			naming_method = frappe.db.get_value("HR Settings", None, "emp_created_by")
			if not naming_method:
				frappe.throw(_("Please setup Employee Naming System in Human Resource > HR Settings"))
			if naming_method == "Naming Series":
				set_name_by_naming_series(self)
			elif naming_method == "Employee Number":
				self.name = self.employee_number
			elif naming_method == "Full Name":
				self.set_employee_name()
				self.name = self.employee_name

		self.employee = self.name

	def validate_duplicate_user_id(self):
		# Allow the same user_id across Companies. Hard-lock per (user_id, company)
		# when status == Active. Sequential rejoin (previous record Inactive/Left) is allowed.
		if not self.user_id:
			return
		duplicate = frappe.db.get_value(
			"Employee",
			{
				"user_id": self.user_id,
				"company": self.company,
				"status": "Active",
				"name": ("!=", self.name or ""),
			},
			"name",
		)
		if duplicate:
			frappe.throw(
				_("User {0} is already mapped to Active Employee {1} in {2}.").format(
					frappe.bold(self.user_id),
					_employee_link(duplicate),
					frappe.bold(self.company),
				),
				frappe.DuplicateEntryError,
			)


def validate_statutory_id_formats(doc, method=None):
	if doc.get("pan_number") and not PAN_RE.match(doc.pan_number):
		frappe.throw(_("PAN must match format AAAAA9999A (5 letters, 4 digits, 1 letter)."))
	if doc.get("uan_number") and not UAN_RE.match(doc.uan_number):
		frappe.throw(_("UAN must be exactly 12 digits."))
	if doc.get("ifsc_code") and not IFSC_RE.match(doc.ifsc_code):
		frappe.throw(_("IFSC must be 4 letters + '0' + 6 alphanumeric (e.g., HDFC0001234)."))

	# Aadhaar: full 12-digit number is the canonical input now. If it's set,
	# validate it AND auto-derive the legacy aadhaar_last_4 column so audits,
	# UAN-Aadhaar linkage checks, and DPDP reports keep working unchanged.
	if doc.get("aadhaar_number"):
		num = str(doc.aadhaar_number).strip()
		if not AADHAAR_FULL_RE.match(num):
			frappe.throw(_("Aadhaar must be exactly 12 digits and start with 2-9."))
		if not verhoeff_check_aadhaar(num):
			frappe.throw(_("Aadhaar checksum failed — please re-check the number."))
		# Always keep the derived last-4 in sync.
		if doc.get("aadhaar_last_4") != num[-4:]:
			doc.aadhaar_last_4 = num[-4:]
	elif doc.get("aadhaar_last_4") and not AADHAAR_LAST4_RE.match(doc.aadhaar_last_4):
		# Legacy path: only the last 4 are present (e.g., pre-migration data).
		frappe.throw(_("Aadhaar Last 4 Digits must be exactly 4 digits."))


def validate_person_data_consistency(doc, method=None):
	# When the same user_id appears on multiple Employee records, person-level
	# fields (PAN, UAN, ESIC IP, Aadhaar last-4, NPS PRAN, DOB, gender) must
	# agree across them. We only flag mismatches between *non-empty* values —
	# a blank on one Employee never contradicts a value on another.
	if not doc.user_id:
		return

	others = frappe.get_all(
		"Employee",
		filters={"user_id": doc.user_id, "name": ("!=", doc.name or "")},
		fields=["name", *PERSON_LEVEL_FIELDS],
	)
	if not others:
		return

	mismatches = []
	for other in others:
		for field in PERSON_LEVEL_FIELDS:
			mine = doc.get(field)
			theirs = other.get(field)
			if mine and theirs and str(mine) != str(theirs):
				mismatches.append((other.name, field, mine, theirs))

	if mismatches:
		lines = [
			_("{0} on Employee {1}: this record has {2}, other has {3}").format(
				frappe.bold(field), _employee_link(other_name), frappe.bold(str(mine)), frappe.bold(str(theirs))
			)
			for other_name, field, mine, theirs in mismatches
		]
		frappe.throw(
			_("Person-level fields must match across Employees linked to the same User:")
			+ "<br>"
			+ "<br>".join(lines),
			title=_("Statutory ID Mismatch"),
		)


def validate_unique_statutory_person(doc, method=None):
	"""PAN and Aadhaar each identify a single human, so the same value must never
	be spread across two *different* people.

	Person identity is keyed on ``user_id`` (the same key the rest of the
	multi-employer model uses): one person legitimately has many Employee records
	across companies that all share the same PAN/Aadhaar, but the same PAN/Aadhaar
	under two *distinct* ``user_id``s is a data-integrity error — a typo, or two
	logins for one human that should be merged.

	Only flagged when both sides carry a (different) non-empty ``user_id``.
	Records that aren't linked to a User yet can't be proven distinct — mirroring
	validate_person_data_consistency — so not-yet-linked bulk imports don't break.
	"""
	if not doc.user_id:
		return
	for field, label in (("pan_number", _("PAN")), ("aadhaar_number", _("Aadhaar"))):
		value = doc.get(field)
		if not value:
			continue
		# Another Employee with the same statutory ID but a different, non-empty
		# user_id (NULL/'' user_ids are excluded by NOT IN, so unlinked records
		# never trip this).
		clash = frappe.db.get_value(
			"Employee",
			{
				field: value,
				"user_id": ("not in", ["", doc.user_id]),
				"name": ("!=", doc.name or ""),
			},
			["name", "user_id"],
			as_dict=True,
		)
		if clash:
			frappe.throw(
				_(
					"{0} {1} is already linked to a different person (Employee {2}, User {3}). "
					"A {0} must belong to exactly one individual."
				).format(label, frappe.bold(str(value)), _employee_link(clash.name), frappe.bold(clash.user_id)),
				title=_("Duplicate {0}").format(label),
			)


def auto_set_primary_employer(doc, method=None):
	"""Auto-tick "Primary Employer for TDS / Form 12B" on a person's first Active
	employment.

	The flag marks which employer consolidates the person's income for TDS /
	Form 12B; there must be exactly one at a time. The first time a person (keyed
	on ``user_id``) appears with no other Active Primary, tick it for them; a
	second concurrent employer is left unticked (they declare it via Form 12B).
	A person who rejoins after leaving (the old record now Inactive) correctly
	gets the new Active job ticked.

	Runs only on insert or when a User first gets linked — the New Employee Setup
	flow inserts the Employee, then links the User on a follow-up save — never on
	ordinary later saves, so an explicit HR untick is respected. No-ops without a
	``user_id`` (no person key) or when the record isn't Active.
	"""
	if doc.get("is_primary_employer"):
		return
	if doc.status != "Active" or not doc.user_id:
		return

	previous = doc.get_doc_before_save()
	is_insert = previous is None
	user_just_linked = bool(previous and not previous.get("user_id") and doc.user_id)
	if not (is_insert or user_just_linked):
		return

	existing_primary = frappe.db.exists(
		"Employee",
		{
			"user_id": doc.user_id,
			"is_primary_employer": 1,
			"status": "Active",
			"name": ("!=", doc.name or ""),
		},
	)
	if not existing_primary:
		doc.is_primary_employer = 1


def validate_single_primary_employer(doc, method=None):
	"""At most one Active Primary Employer per person.

	The person is matched by BOTH ``user_id`` (the login) and ``pan_number`` (the
	tax identity), so the guard holds even for records that don't have a User
	linked yet — two same-PAN records can't both be Primary.

	Enforced only when the flag is being turned *on* (insert with it set, or a
	0->1 transition). Editing a record that was already Primary is never blocked,
	so a pre-existing (possibly already-conflicting) legacy primary doesn't wedge
	unrelated saves; the backfill report surfaces legacy conflicts instead.
	"""
	if not doc.get("is_primary_employer"):
		return
	previous = doc.get_doc_before_save()
	if previous and previous.get("is_primary_employer"):
		# Was already Primary before this save — don't re-litigate legacy state.
		return

	for field, label in (("user_id", _("User")), ("pan_number", _("PAN"))):
		value = doc.get(field)
		if not value:
			continue
		other = frappe.db.get_value(
			"Employee",
			{
				field: value,
				"is_primary_employer": 1,
				"status": "Active",
				"name": ("!=", doc.name or ""),
			},
			"name",
		)
		if other:
			frappe.throw(
				_(
					"Employee {0} is already the Primary Employer for this person ({1} {2}). "
					"Only one Primary Employer at a time."
				).format(_employee_link(other), label, frappe.bold(str(value))),
				title=_("Duplicate Primary Employer"),
			)


def _backfill_primary_employer(dry_run=True):
	"""Tick "Primary Employer for TDS / Form 12B" for every person who has a
	single Active employment and a PAN — the unambiguous cases — and leave anyone
	with concurrent employments for HR to resolve by hand.

	A person is identified by ``pan_number`` and ``user_id``. A record is ticked
	only when it is Active, carries a PAN, isn't already Primary, and *no other
	Active Employee* shares either its PAN or its user_id — i.e. it is provably the
	person's only live job, so naming it Primary can't be wrong. Records sharing a
	PAN or user_id with another Active record are the Form 12B / multi-employer
	cases and are reported, not touched.

	Also surfaces (never auto-fixes) two integrity problems the guards would now
	block but legacy data may already contain: the same PAN/Aadhaar spread across
	*different* user_ids, and a person who somehow already has more than one Active
	Primary. Returns a summary dict; writes only when ``dry_run`` is false.
	"""
	from collections import defaultdict

	actives = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "user_id", "pan_number", "aadhaar_number", "is_primary_employer"],
	)

	pan_count = defaultdict(int)
	user_count = defaultdict(int)
	pan_users = defaultdict(set)
	aadhaar_users = defaultdict(set)
	pan_primaries = defaultdict(list)
	user_primaries = defaultdict(list)
	for e in actives:
		if e.pan_number:
			pan_count[e.pan_number] += 1
		if e.user_id:
			user_count[e.user_id] += 1
		if e.pan_number and e.user_id:
			pan_users[e.pan_number].add(e.user_id)
		if e.aadhaar_number and e.user_id:
			aadhaar_users[e.aadhaar_number].add(e.user_id)
		if e.is_primary_employer:
			if e.pan_number:
				pan_primaries[e.pan_number].append(e.name)
			if e.user_id:
				user_primaries[e.user_id].append(e.name)

	eligible, skipped_multi = [], []
	skipped_no_pan = skipped_already_primary = 0
	for e in actives:
		if e.is_primary_employer:
			skipped_already_primary += 1
			continue
		if not e.pan_number:
			skipped_no_pan += 1
			continue
		shares_pan = pan_count[e.pan_number] > 1
		shares_user = bool(e.user_id) and user_count[e.user_id] > 1
		if shares_pan or shares_user:
			skipped_multi.append({"name": e.name, "pan": e.pan_number, "user_id": e.user_id})
			continue
		eligible.append({"name": e.name, "pan": e.pan_number, "user_id": e.user_id})

	# Integrity conflicts — reported for HR, never auto-resolved.
	conflicts = {
		"pan_across_users": {k: sorted(v) for k, v in pan_users.items() if len(v) > 1},
		"aadhaar_across_users": {k: sorted(v) for k, v in aadhaar_users.items() if len(v) > 1},
		"multiple_primaries_per_pan": {k: v for k, v in pan_primaries.items() if len(v) > 1},
		"multiple_primaries_per_user": {k: v for k, v in user_primaries.items() if len(v) > 1},
	}

	if not dry_run and eligible:
		for row in eligible:
			frappe.db.set_value("Employee", row["name"], "is_primary_employer", 1, update_modified=False)
		frappe.db.commit()

	return {
		"dry_run": bool(dry_run),
		"active_total": len(actives),
		("ticked" if not dry_run else "would_tick"): eligible,
		"eligible_count": len(eligible),
		"skipped_multi": skipped_multi,
		"skipped_multi_count": len(skipped_multi),
		"skipped_no_pan": skipped_no_pan,
		"skipped_already_primary": skipped_already_primary,
		"conflicts": conflicts,
		"has_conflicts": any(conflicts.values()),
	}


@frappe.whitelist()
def backfill_primary_employer(dry_run=1):
	"""HR-triggerable backfill of the Primary Employer flag (see
	_backfill_primary_employer). Defaults to a dry run that only reports what it
	*would* do; pass dry_run=0 to actually write."""
	frappe.only_for(("HR Manager", "HR User", "System Manager"))
	return _backfill_primary_employer(dry_run=cint(dry_run))


def _hr_setting(fieldname):
	"""Read an HR Settings value, returning None if that field hasn't been
	created on this site yet.

	Several HR Settings fields are app custom fields added by patches. On a site
	where those patches haven't migrated, frappe.db.get_single_value throws
	"Field ... does not exist on HR Settings" and blocks whatever save triggered
	the read. Treating a missing field as unset keeps the feature dormant instead
	of hard-failing core Employee saves.
	"""
	if not frappe.get_meta("HR Settings").get_field(fieldname):
		return None
	return frappe.db.get_single_value("HR Settings", fieldname)


# ---------------------------------------------------------------------------
# Biometric / Attendance Device ID assignment
# ---------------------------------------------------------------------------
# attendance_device_id (erpnext Employee, Data, unique, no_copy) is the
# biometric / RF-tag identifier that maps device punches to an Employee.
# HR Settings.biometric_id_mode governs how it gets filled:
#   "Manual"            -> HR types it; no auto-generation (default).
#   "Hybrid"            -> HR may type it OR click Generate (auto gap-fill).
#   "Auto (Compulsory)" -> system assigns the next free number on save; the
#                          field is read-only for non-System-Managers.
# Once a value is set it is LOCKED: only a System Manager may change or clear
# it, so an established attendance mapping can't be silently reassigned.
BIOMETRIC_ID_FIELD = "attendance_device_id"


def _biometric_id_mode():
	return _hr_setting("biometric_id_mode") or "Manual"


def _next_free_biometric_id():
	"""Smallest free positive integer not already used as an attendance_device_id.

	Gap-filling and global (the field is unique across every Employee), so
	1,2,3,5 -> 4 and 555,557 -> 556. Only purely-numeric existing IDs take part
	in the sequence; manually-entered alphanumeric tags are ignored.
	"""
	used = set()
	for value in frappe.get_all(
		"Employee",
		filters={BIOMETRIC_ID_FIELD: ("is", "set")},
		pluck=BIOMETRIC_ID_FIELD,
	):
		value = (value or "").strip()
		if value.isdigit():
			used.add(int(value))
	n = 1
	while n in used:
		n += 1
	return str(n)


@frappe.whitelist()
def generate_biometric_id():
	"""Return the next free biometric ID for the Generate button.

	Gated on Employee write permission so it can't be used to enumerate the
	table. Uniqueness is ultimately enforced by the field's unique index — if a
	racing save grabs the same number first, the second save fails cleanly and
	the user can regenerate.
	"""
	if not frappe.has_permission("Employee", "write"):
		frappe.throw(_("Not permitted to generate a Biometric ID."), frappe.PermissionError)
	return _next_free_biometric_id()


def apply_biometric_id_rules(doc, method=None):
	"""Enforce the HR Settings biometric ID policy on Employee save.

	1. Lock-once-set: a non-empty attendance_device_id may only be changed or
	   cleared by a System Manager.
	2. Auto (Compulsory): auto-fill the next free number when the field is empty.
	"""
	before = doc.get_doc_before_save()
	old_value = ((before.get(BIOMETRIC_ID_FIELD) if before else "") or "").strip()
	new_value = (doc.get(BIOMETRIC_ID_FIELD) or "").strip()

	if old_value and new_value != old_value and "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("The Biometric / Attendance Device ID is locked once set. Only a System Manager can change it."),
			title=_("Not Permitted"),
		)

	if not new_value and _biometric_id_mode() == "Auto (Compulsory)":
		doc.set(BIOMETRIC_ID_FIELD, _next_free_biometric_id())


def apply_address_copy_rules(doc, method=None):
	"""Mirror current_address into permanent_address when the HR toggle is set.

	Driven from the convenience Check custom field
	(permanent_address_same_as_current). Enforced here so the copy is correct for
	Data Import / API writes too, not just the live employee.js handler.
	"""
	if doc.get("permanent_address_same_as_current"):
		doc.permanent_address = doc.current_address


def auto_set_probation_schedule(doc, method=None):
	"""On Employee validate, if confirmation_status is 'Probation' and the
	Scheduled Confirmation Date is empty, fill it from
	date_of_joining + HR Settings.default_probation_period_days.

	No-ops when scheduled_confirmation_date is already set (HR override),
	when confirmation_status isn't Probation, or when date_of_joining is missing.
	"""
	if doc.get("confirmation_status") != "Probation":
		return
	if doc.get("scheduled_confirmation_date"):
		return
	if not doc.get("date_of_joining"):
		return
	days = _hr_setting("default_probation_period_days")
	if not days or int(days) <= 0:
		return
	from frappe.utils import add_days

	doc.scheduled_confirmation_date = add_days(getdate(doc.date_of_joining), int(days))


def validate_onboarding_process(doc, method=None):
	"""Validates Employee Creation for linked Employee Onboarding"""
	if not doc.job_applicant:
		return

	employee_onboarding = frappe.get_all(
		"Employee Onboarding",
		filters={
			"job_applicant": doc.job_applicant,
			"docstatus": 1,
			"boarding_status": ("!=", "Completed"),
		},
	)
	if employee_onboarding:
		onboarding = frappe.get_doc("Employee Onboarding", employee_onboarding[0].name)
		onboarding.validate_employee_creation()
		onboarding.db_set("employee", doc.name)


def publish_update(doc, method=None):
	import indian_hrms_compliance

	indian_hrms_compliance.refetch_resource("indian_hrms_compliance:employee", doc.user_id)


def update_job_applicant_and_offer(doc, method=None):
	"""Updates Job Applicant and Job Offer status as 'Accepted' and submits them"""
	if not doc.job_applicant:
		return

	applicant_status_before_change = frappe.db.get_value("Job Applicant", doc.job_applicant, "status")
	if applicant_status_before_change != "Accepted":
		frappe.db.set_value("Job Applicant", doc.job_applicant, "status", "Accepted")
		frappe.msgprint(
			_("Updated the status of linked Job Applicant {0} to {1}").format(
				get_link_to_form("Job Applicant", doc.job_applicant), frappe.bold(_("Accepted"))
			)
		)
	offer_status_before_change = frappe.db.get_value(
		"Job Offer", {"job_applicant": doc.job_applicant, "docstatus": ["!=", 2]}, "status"
	)
	if offer_status_before_change and offer_status_before_change != "Accepted":
		job_offer = frappe.get_last_doc("Job Offer", filters={"job_applicant": doc.job_applicant})
		job_offer.status = "Accepted"
		job_offer.flags.ignore_mandatory = True
		job_offer.flags.ignore_permissions = True
		job_offer.save()

		msg = _("Updated the status of Job Offer {0} for the linked Job Applicant {1} to {2}").format(
			get_link_to_form("Job Offer", job_offer.name),
			frappe.bold(doc.job_applicant),
			frappe.bold(_("Accepted")),
		)
		if job_offer.docstatus == 0:
			msg += "<br>" + _("You may add additional details, if any, and submit the offer.")

		frappe.msgprint(msg)


def update_approver_role(doc, method=None):
	"""Adds relevant approver role for the user linked to the approver Employee"""
	leave_approver_user = resolve_employee_approver(doc.leave_approver)
	if leave_approver_user:
		user = frappe.get_doc("User", leave_approver_user)
		user.flags.ignore_permissions = True
		user.add_roles("Leave Approver")

	expense_approver_user = resolve_employee_approver(doc.expense_approver)
	if expense_approver_user:
		user = frappe.get_doc("User", expense_approver_user)
		user.flags.ignore_permissions = True
		user.add_roles("Expense Approver")


def auto_assign_leave_policy_on_activation(doc, method=None):
	"""When an Employee becomes Active, auto-assign the company's default Leave
	Policy. Submitting the Leave Policy Assignment cascades into Leave
	Allocations, so this collapses the leave-setup chain to zero clicks.

	Opt-in via HR Settings.auto_assign_leave_policy_on_activation, using the
	per-company Company.default_leave_policy and the Fiscal-Year-derived Leave
	Period (get_current_leave_period). Idempotent (skips if an overlapping
	assignment exists) and never blocks the Employee
	save — failures are logged, not raised.
	"""
	if doc.status != "Active":
		return
	# The New Employee Setup page assigns the Leave Policy HR explicitly chose,
	# so don't also fire the company-default auto-assignment underneath it.
	if frappe.flags.get("in_new_employee_setup"):
		return
	# Opt-in toggle is an app custom field; treat a missing field as OFF so a
	# partially-migrated site never hard-blocks the Employee save (see _hr_setting).
	if not cint(_hr_setting("auto_assign_leave_policy_on_activation")):
		return

	# Act only on the transition into Active, not on every later save.
	previous = doc.get_doc_before_save()
	if previous and previous.status == "Active":
		return

	if not doc.company:
		return
	leave_policy = frappe.get_cached_value("Company", doc.company, "default_leave_policy")
	if not leave_policy:
		return

	# The leave period is derived from the Fiscal Year (India), not stored per
	# company.
	from indian_hrms_compliance.hr.leave_period_setup import get_current_leave_period

	leave_period = get_current_leave_period()
	if not leave_period:
		return
	period = frappe.db.get_value("Leave Period", leave_period, ["from_date", "to_date"], as_dict=True)
	if not period:
		return

	# Idempotent: skip if an overlapping (non-cancelled) assignment already exists.
	from indian_hrms_compliance.hr.utils import has_overlapping_leave_assignment

	if has_overlapping_leave_assignment(doc.name, period.from_date, period.to_date):
		return

	from indian_hrms_compliance.hr.doctype.leave_policy_assignment.leave_policy_assignment import (
		create_assignment,
	)

	savepoint = "auto_leave_policy_assignment"
	try:
		frappe.db.savepoint(savepoint)
		assignment = create_assignment(
			doc.name,
			frappe._dict(
				assignment_based_on="Leave Period",
				leave_policy=leave_policy,
				leave_period=leave_period,
				effective_from=period.from_date,
				effective_to=period.to_date,
				carry_forward=0,
			),
		)
		assignment.submit()
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		frappe.log_error(
			title="Auto Leave Policy Assignment failed",
			message=f"Employee: {doc.name}\n{frappe.get_traceback()}",
		)
		return

	frappe.msgprint(
		_("Leave Policy {0} auto-assigned to {1} for {2}.").format(
			frappe.bold(leave_policy),
			frappe.bold(doc.employee_name or doc.name),
			frappe.bold(leave_period),
		),
		alert=True,
		indicator="green",
	)


def enroll_in_active_policies_on_activation(doc, method=None):
	"""On the transition into Active, create pending acknowledgements for every
	active policy the new employee is in scope for — closes the gap where joiners
	added after a policy was published would otherwise never get an ack. Never
	blocks the Employee save."""
	if doc.status != "Active":
		return
	# During New Employee Setup, HR curates exactly which policies the new joiner
	# acknowledges, so the page enrols that subset itself — don't blanket-enrol here.
	if frappe.flags.get("in_new_employee_setup"):
		return
	previous = doc.get_doc_before_save()
	if previous and previous.status == "Active":
		return

	from indian_hrms_compliance.hr.doctype.hrms_policy.hrms_policy import (
		create_acknowledgements_for_employee,
	)

	savepoint = "enroll_active_policies"
	try:
		frappe.db.savepoint(savepoint)
		created = create_acknowledgements_for_employee(doc.name)
	except Exception:
		try:
			frappe.db.rollback(save_point=savepoint)
		except Exception:
			pass
		frappe.log_error(
			title="Policy acknowledgement enrollment failed",
			message=f"Employee: {doc.name}\n{frappe.get_traceback()}",
		)
		return

	if created:
		frappe.msgprint(
			_("Queued {0} policy acknowledgement(s) for {1}.").format(
				created, frappe.bold(doc.employee_name or doc.name)
			),
			alert=True,
			indicator="blue",
		)


@frappe.whitelist()
def get_employee_readiness(employee: str) -> dict:
	"""Full HR-setup readiness checklist for an Employee, grouped by category.

	Each item: label, done, critical, hint, route (Desk). `score.ready` is True
	only when every *critical* item is done. Drives the Employee form tab, the
	onboarding panel, and the cockpit's readiness aggregate.
	"""
	emp = frappe.db.get_value(
		"Employee",
		employee,
		[
			"name", "employee_name", "company", "user_id", "status", "designation",
			"pan_number", "aadhaar_last_4", "uan_number", "bank_ac_no", "ifsc_code",
			"reports_to", "leave_approver", "expense_approver", "default_shift", "holiday_list",
		],
		as_dict=True,
	)
	if not emp:
		return {}

	def has(doctype, filters):
		return bool(frappe.db.exists(doctype, filters))

	emp_filter = {"employee": employee, "docstatus": ("<", 2)}
	holiday_ok = bool(emp.holiday_list) or bool(
		frappe.db.get_value("Company", emp.company, "default_holiday_list")
	)
	# KRAs/Tasks for this role: an Active HRMS Task targeting all-active or the
	# employee's designation, or a Task Instance already assigned to them.
	role_tasks = has("HRMS Task", {"company": emp.company, "status": "Active", "applicable_to_all_active": 1}) or (
		emp.designation
		and has("HRMS Task", {"company": emp.company, "status": "Active", "assigned_to_designation": emp.designation})
	)
	has_task_instances = has("Goal", {"goal_type": "Task Instance", "employee": employee})
	policies_pending = frappe.db.count(
		"Employee Policy Acknowledgement", {"employee": employee, "status": "Pending"}
	)

	def item(label, done, critical=False, route=None, hint=""):
		return {"label": _(label), "done": bool(done), "critical": critical, "route": route, "hint": _(hint) if hint else ""}

	# Shift: default_shift OR a *submitted* Shift Assignment. The hint states
	# which one satisfied it, so a default-shift tick isn't mistaken for an
	# actual assignment.
	shift_assigned = has("Shift Assignment", {"employee": employee, "docstatus": 1})
	shift_done = bool(emp.default_shift) or shift_assigned
	if emp.default_shift:
		shift_hint = _("Default shift: {0}").format(emp.default_shift)
	elif shift_assigned:
		shift_hint = _("Shift assignment in place")
	else:
		shift_hint = _("Set a default shift or a shift assignment")

	emp_form = ["Form", "Employee", employee]
	categories = [
		{
			"name": _("Identity & Access"),
			"items": [
				item("User account linked", emp.user_id, True, emp_form, "Needed for ESS / PWA login"),
				item("PAN captured", emp.pan_number, False, emp_form, "Recommended for TDS / Form 16"),
				item("Bank account & IFSC", emp.bank_ac_no and emp.ifsc_code, True, emp_form, "Needed for salary payout"),
				item("Aadhaar (last 4)", emp.aadhaar_last_4, False, emp_form),
				item("UAN captured", emp.uan_number, False, emp_form, "For PF / ECR"),
			],
		},
		{
			"name": _("Reporting & Approvers"),
			"items": [
				item("Reporting manager", emp.reports_to, False, emp_form),
				item("Leave approver", emp.leave_approver, True, emp_form),
				item("Expense approver", emp.expense_approver, False, emp_form),
			],
		},
		{
			"name": _("Leave & Holidays"),
			"items": [
				item("Leave Policy assigned", has("Leave Policy Assignment", emp_filter), True,
					 ["List", "Leave Policy Assignment", {"employee": employee}]),
				item("Leave allocated", has("Leave Allocation", {"employee": employee, "docstatus": 1}), False,
					 ["List", "Leave Allocation", {"employee": employee}]),
				item("Holiday List set", holiday_ok, True, emp_form, "On the employee or the company default"),
			],
		},
		{
			"name": _("Payroll"),
			"items": [
				item("Salary Structure assigned", has("Salary Structure Assignment", emp_filter), True,
					 ["List", "Salary Structure Assignment", {"employee": employee}]),
			],
		},
		{
			"name": _("Shift"),
			"items": [
				{
					"label": _("Shift configured"),
					"done": shift_done,
					"critical": False,
					"route": ["List", "Shift Assignment", {"employee": employee}],
					"hint": shift_hint,
				},
			],
		},
		{
			"name": _("KRAs & Tasks"),
			"items": [
				item("KRAs / Tasks defined for role", role_tasks, False,
					 ["List", "HRMS Task", {"company": emp.company}],
					 "Active HRMS Task for this designation or all-active"),
				item("Task instances assigned", has_task_instances, False,
					 ["List", "Goal", {"goal_type": "Task Instance", "employee": employee}]),
			],
		},
		{
			"name": _("Policies"),
			"items": [
				item("Company policies acknowledged", policies_pending == 0, True,
					 ["List", "Employee Policy Acknowledgement", {"employee": employee, "status": "Pending"}],
					 "No pending acknowledgements"),
			],
		},
	]

	flat = [i for c in categories for i in c["items"]]
	total = len(flat)
	done = sum(1 for i in flat if i["done"])
	critical_open = [i for i in flat if i["critical"] and not i["done"]]
	score = {
		"done": done,
		"total": total,
		"pct": round(done / total * 100) if total else 0,
		"ready": not critical_open,
		"critical_open": len(critical_open),
	}
	return {
		"employee": emp.name,
		"employee_name": emp.employee_name or employee,
		"company": emp.company,
		"status": emp.status,
		"score": score,
		"categories": categories,
		"items": flat,
	}


@frappe.whitelist()
def get_employee_readiness_summary(company: str | None = None) -> dict:
	"""Company-wide readiness aggregate (set-based, no per-employee loop).
	Returns how many Active employees are fully ready vs incomplete, and the
	count missing each critical check."""
	emp_filter = {"status": "Active"}
	if company:
		emp_filter["company"] = company

	emps = set(frappe.get_all("Employee", filters=emp_filter, pluck="name"))
	if not emps:
		return {"total": 0, "ready": 0, "incomplete": 0, "pct": 0, "missing": {}}

	def field_set(field):
		return emps & set(frappe.get_all("Employee", filters={**emp_filter, field: ("is", "set")}, pluck="name"))

	has_user = field_set("user_id")
	has_pan = field_set("pan_number")
	has_la = field_set("leave_approver")
	bank = field_set("bank_ac_no") & field_set("ifsc_code")

	if company and frappe.db.get_value("Company", company, "default_holiday_list"):
		has_holiday = set(emps)
	else:
		has_holiday = field_set("holiday_list")

	with_lpa = emps & set(frappe.get_all("Leave Policy Assignment", filters={"docstatus": ("<", 2)}, pluck="employee"))
	with_ssa = emps & set(frappe.get_all("Salary Structure Assignment", filters={"docstatus": ("<", 2)}, pluck="employee"))
	pending_ack = emps & set(frappe.get_all("Employee Policy Acknowledgement", filters={"status": "Pending"}, pluck="employee"))

	ready = has_user & has_pan & bank & has_la & has_holiday & with_lpa & with_ssa & (emps - pending_ack)
	missing = {
		"User login": len(emps - has_user),
		"PAN": len(emps - has_pan),
		"Bank details": len(emps - bank),
		"Leave approver": len(emps - has_la),
		"Holiday List": len(emps - has_holiday),
		"Leave Policy": len(emps - with_lpa),
		"Salary Structure": len(emps - with_ssa),
		"Policy acknowledgement": len(pending_ack),
	}
	return {
		"total": len(emps),
		"ready": len(ready),
		"incomplete": len(emps - ready),
		"pct": round(len(ready) / len(emps) * 100),
		"missing": missing,
	}


@frappe.whitelist()
def get_employee_setup_status(employee: str) -> dict:
	"""Back-compat flat shape for the onboarding panel — delegates to the full
	readiness checklist."""
	data = get_employee_readiness(employee)
	if not data:
		return {}
	return {
		"employee_name": data["employee_name"],
		"score": data["score"],
		"items": [{"label": i["label"], "done": i["done"], "route": i["route"]} for i in data["items"]],
	}


def update_approver_user_roles(doc, method=None):
	# doc is a User being saved; the approver fields now store Employee names, so
	# find Employees whose approver is one of this user's own Employee records.
	own_employees = frappe.get_all("Employee", filters={"user_id": doc.name}, pluck="name")
	if not own_employees:
		return

	approver_roles = set()
	if frappe.db.exists("Employee", {"leave_approver": ("in", own_employees)}):
		approver_roles.add("Leave Approver")

	if frappe.db.exists("Employee", {"expense_approver": ("in", own_employees)}):
		approver_roles.add("Expense Approver")

	if approver_roles:
		doc.append_roles(*approver_roles)


def update_employee_transfer(doc, method=None):
	"""Unsets Employee ID in Employee Transfer if doc is deleted"""
	if frappe.db.exists("Employee Transfer", {"new_employee_id": doc.name, "docstatus": 1}):
		emp_transfer = frappe.get_doc("Employee Transfer", {"new_employee_id": doc.name, "docstatus": 1})
		emp_transfer.db_set("new_employee_id", "")


@frappe.whitelist()
def get_timeline_data(doctype, name):
	"""Return timeline for attendance"""
	from frappe.desk.notifications import get_open_count

	out = {}

	open_count = get_open_count(doctype, name)
	out["count"] = open_count["count"]

	timeline_data = dict(
		frappe.db.sql(
			"""
			select unix_timestamp(attendance_date), count(*)
			from `tabAttendance` where employee=%s
			and attendance_date > date_sub(curdate(), interval 1 year)
			and status in ('Present', 'Half Day')
			group by attendance_date""",
			name,
		)
	)

	out["timeline_data"] = timeline_data
	return out


@frappe.whitelist()
def get_retirement_date(date_of_birth=None):
	if date_of_birth:
		try:
			retirement_age = cint(frappe.db.get_single_value("HR Settings", "retirement_age") or 60)
			dt = add_years(getdate(date_of_birth), retirement_age)
			return dt.strftime("%Y-%m-%d")
		except ValueError:
			# invalid date
			return
