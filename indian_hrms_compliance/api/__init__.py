import frappe
from frappe import _
from frappe.model import get_permitted_fields
from frappe.model.workflow import get_workflow_name
from frappe.query_builder import Order
from frappe.utils import add_days, cint, date_diff, flt, getdate, now_datetime, strip_html

from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

from indian_hrms_compliance.overrides.employee_master import resolve_employee_approver

# ---------------------------------------------------------------------------
# Real-time refresh helpers — used by all PWA-facing mutations.
# ---------------------------------------------------------------------------
#
# The PWA's socket handler (frontend/src/socket.js) listens for the event
# "indian_hrms_compliance:refetch_resource" carrying a {cache_key} payload and
# calls .reload() on the matching frappe-ui resource. Every state-changing
# endpoint (approve/reject/submit/withdraw/create/...) publishes one of these
# to keep open screens fresh without a manual pull-to-refresh.
#
# Routing rules:
#   * Approver-targeted (per-user, narrow): the approving HR/manager's inbox
#     + summary should re-pull right after their action.
#   * Requester-targeted (per-user, narrow): the employee whose request was
#     acted on should see the consequence (their leaves / claims / exit
#     dashboard / etc.) without refreshing.
#   * HR-targeted (small fan-out): when a new request lands, every HR user's
#     inbox should bump.
#   * Broadcast (user=None): only for org-wide data (Org Attendance) where
#     enumerating recipients isn't worth the SQL.
#
# Failures are swallowed — a websocket hiccup must NEVER undo a committed DB
# write. The user can always pull-to-refresh.


def _pwa_refetch(cache_keys: "str | list[str]", user: str | None = None) -> None:
	if isinstance(cache_keys, str):
		cache_keys = [cache_keys]
	for key in cache_keys:
		try:
			frappe.publish_realtime(
				"indian_hrms_compliance:refetch_resource",
				{"cache_key": key},
				user=user,
				after_commit=True,
			)
		except Exception:
			pass


_INBOX_CACHE_KEYS = (
	"indian_hrms_compliance:pending_approvals",
	"indian_hrms_compliance:approvals_summary",
)


_ORG_ATT_REFETCH_FLAG = "_ihc_org_att_published"
_ORG_ATT_RECIPIENTS_FLAG = "_ihc_org_att_recipients"


def _resolve_org_attendance_recipients() -> set[str]:
	"""All Users who might be viewing the Org Attendance roll-call:
	  * HR Manager / HR User holders (the "see all" path), and
	  * Users whose Employee has at least one Active direct report (the "team" path).

	Cached on frappe.local per request — biometric imports fire the hook
	hundreds of times in one request and we don't want to re-query each time.
	"""
	cached = getattr(frappe.local, _ORG_ATT_RECIPIENTS_FLAG, None)
	if cached is not None:
		return cached

	recipients: set[str] = set()

	# HR roles
	hr_users = frappe.get_all(
		"Has Role",
		filters={"role": ("in", ("HR Manager", "HR User", "System Manager"))},
		pluck="parent",
	)
	recipients.update(u for u in hr_users if u and u not in ("Administrator", "Guest"))

	# Reporting managers with at least one Active direct report.
	manager_users = frappe.db.sql_list(
		"""
		SELECT DISTINCT m.user_id
		FROM `tabEmployee` m
		JOIN `tabEmployee` r ON r.reports_to = m.name
		WHERE m.status = 'Active'
		  AND r.status = 'Active'
		  AND m.user_id IS NOT NULL
		  AND m.user_id != ''
		"""
	) or []
	recipients.update(u for u in manager_users if u and u not in ("Administrator", "Guest"))

	try:
		setattr(frappe.local, _ORG_ATT_RECIPIENTS_FLAG, recipients)
	except Exception:
		pass
	return recipients


def publish_org_attendance_refetch(doc=None, method=None) -> None:
	"""doc_events hook target — push a refetch of the Org Attendance roll-call
	to every user who might be viewing it (HR + reporting managers).

	Why per-user fan-out instead of a single ``user=None`` broadcast: Frappe's
	socket.io server auto-joins the ``"all"`` room only for ``user_type ==
	"System User"`` (see realtime/handlers/frappe_handlers.js). A user=None
	broadcast routes to ``"all"``, which means Website-User HRs (rare) and any
	other non-System-User who can view this screen would silently miss it.
	Per-user push targets their personal room, which every authenticated
	socket joins on connection — reliable regardless of user_type.

	In-request debounce via frappe.local: biometric imports + bulk leave
	approvals fire this hundreds of times in one request — we want one
	publish per recipient per request, not N. The recipients query is also
	cached on frappe.local so we don't re-enumerate per call.
	"""
	if getattr(frappe.local, _ORG_ATT_REFETCH_FLAG, False):
		return
	try:
		setattr(frappe.local, _ORG_ATT_REFETCH_FLAG, True)
	except Exception:
		pass
	for user in _resolve_org_attendance_recipients():
		_pwa_refetch("indian_hrms_compliance:org_attendance_today", user=user)


def _broadcast_hr_inbox_refresh() -> None:
	"""All HR-role users refresh their inbox. Small fan-out — HR teams are small."""
	hr_users = frappe.get_all(
		"Has Role",
		filters={"role": ("in", ("HR Manager", "HR User"))},
		pluck="parent",
	)
	for u in {u for u in hr_users if u and u not in ("Administrator", "Guest")}:
		_pwa_refetch(list(_INBOX_CACHE_KEYS), user=u)


# Per-doctype cache keys to refresh for the REQUESTER after their request is
# acted on (approved or rejected). Empty list = nothing employee-side to refresh.
_REQUESTER_CACHE_KEYS_BY_DOCTYPE: dict[str, tuple[str, ...]] = {
	"Leave Application": (
		"indian_hrms_compliance:my_leaves",
		"indian_hrms_compliance:leave_balance",
	),
	"Expense Claim": (
		"indian_hrms_compliance:my_claims",
		"indian_hrms_compliance:expense_claim_summary",
	),
	"Employee Advance": ("indian_hrms_compliance:employee_advance_balance",),
	"Shift Request": ("indian_hrms_compliance:my_shift_requests",),
	"Attendance Request": ("indian_hrms_compliance:my_attendance_requests",),
	"Resignation Request": (
		"indian_hrms_compliance:my_resignation_status",
		"indian_hrms_compliance:my_exit_clearance",
		"indian_hrms_compliance:my_exit_documents",
	),
	"Goal": (
		"indian_hrms_compliance:my_tasks",
		"indian_hrms_compliance:my_tasks_dashboard",
		"indian_hrms_compliance:my_task_summary",
	),
	"Employee Grievance": ("indian_hrms_compliance:my_grievances",),
	# Profile Change + Onboarding Application don't have a per-employee resource
	# on the PWA today; their consequence (Employee record changes) auto-pushes
	# via the Employee list_update subscription used by Profile.vue.
	"Employee Profile Change Request": (),
	"Employee Onboarding Application": (),
}


def _refresh_requester(doctype: str, requester_user: str | None) -> None:
	if not requester_user:
		return
	keys = _REQUESTER_CACHE_KEYS_BY_DOCTYPE.get(doctype, ())
	if keys:
		_pwa_refetch(list(keys), user=requester_user)


SUPPORTED_FIELD_TYPES = [
	"Link",
	"Select",
	"Small Text",
	"Text",
	"Long Text",
	"Text Editor",
	"Table",
	"Check",
	"Data",
	"Float",
	"Int",
	"Section Break",
	"Date",
	"Time",
	"Datetime",
	"Currency",
]


@frappe.whitelist()
def get_current_user_info() -> dict:
	current_user = frappe.session.user
	user = frappe.db.get_value(
		"User", current_user, ["name", "first_name", "full_name", "user_image"], as_dict=True
	)
	user["roles"] = frappe.get_roles(current_user)

	return user


EMPLOYEE_CONTEXT_FIELDS = [
	"name",
	"first_name",
	"employee_name",
	"designation",
	"department",
	"company",
	"reports_to",
	"user_id",
	"image",
	"is_primary_employer",
]


@frappe.whitelist()
def get_my_employees() -> list[dict]:
	"""All Active Employee records linked to the current user.

	A single User may map to multiple Employees across Companies
	(see multi-employee architecture). The PWA uses this to populate the
	company/employee switcher. Primary Employer is surfaced first.
	"""
	return frappe.get_all(
		"Employee",
		filters={"user_id": frappe.session.user, "status": "Active"},
		fields=EMPLOYEE_CONTEXT_FIELDS,
		order_by="is_primary_employer desc, creation asc",
	)


def get_active_employee_name() -> str | None:
	"""Resolve the Employee the PWA currently operates as, for a multi-employed
	user. Resolution order:
	  1. The user's stored 'active_employee' default, if still valid
	     (Active + still linked to this user).
	  2. The Primary Employer Employee.
	  3. The earliest-created Active Employee.
	Returns None when the user has no Active Employee.
	"""
	employees = get_my_employees()
	if not employees:
		return None

	valid_names = {e.name for e in employees}
	selected = frappe.defaults.get_user_default("active_employee")
	if selected and selected in valid_names:
		return selected

	for e in employees:
		if e.get("is_primary_employer"):
			return e.name
	return employees[0].name


@frappe.whitelist()
def get_current_employee_info() -> dict:
	"""The active Employee context for the PWA. Multi-employment aware —
	resolves via get_active_employee_name() rather than picking an arbitrary
	row, and tags whether the user has more than one employment so the
	frontend knows to show the switcher."""
	name = get_active_employee_name()
	if not name:
		return {}

	employee = frappe.db.get_value(
		"Employee", name, EMPLOYEE_CONTEXT_FIELDS, as_dict=True
	)
	if employee:
		all_employees = get_my_employees()
		employee["employment_count"] = len(all_employees)
		employee["has_multiple_employments"] = len(all_employees) > 1
	return employee


@frappe.whitelist()
def set_active_employee(employee: str) -> dict:
	"""Switch the PWA's active Employee context. Validates that the chosen
	Employee is Active and belongs to the current user, then persists the
	choice as a per-user default so it survives across sessions."""
	is_owned = frappe.db.exists(
		"Employee",
		{"name": employee, "user_id": frappe.session.user, "status": "Active"},
	)
	if not is_owned:
		frappe.throw(
			_("You are not linked to an Active Employee record {0}.").format(employee),
			frappe.PermissionError,
		)
	frappe.defaults.set_user_default("active_employee", employee)
	return get_current_employee_info()


@frappe.whitelist()
def get_all_employees() -> list[dict]:
	# Directory of real staff — exclude virtual (management-only) records.
	from indian_hrms_compliance.overrides.employee_master import exclude_virtual

	return frappe.get_list(
		"Employee",
		filters=exclude_virtual(),
		fields=[
			"name",
			"employee_name",
			"designation",
			"department",
			"company",
			"reports_to",
			"user_id",
			"image",
			"status",
		],
		limit=999999,
	)


def get_current_employee() -> str:
	"""The active Employee name for the current user (multi-employment aware).
	Used by every employee-scoped API method below."""
	employee = get_active_employee_name()
	if not employee:
		frappe.throw(_("Employee not found"), frappe.PermissionError)
	return employee


# HR Settings
def _todays_shift_type_flags(employee: str) -> list[dict]:
	"""Mobile check-in flags for every Shift Type the employee is on today.

	Resolved at day level (today's active Shift Assignments plus any legacy
	Employee.default_shift fallback) rather than the current instant, so the
	PWA check-in surface stays stable across the whole shift instead of vanishing
	outside the punch window. This mirrors how a real check-in resolves its
	shift (assignment first, default_shift fallback)."""
	today = getdate()
	shift_types = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": employee,
			"docstatus": 1,
			"status": "Active",
			"start_date": ["<=", today],
		},
		or_filters=[["end_date", ">=", today], ["end_date", "is", "not set"]],
		pluck="shift_type",
	)
	default_shift = frappe.db.get_value("Employee", employee, "default_shift")
	if default_shift:
		shift_types.append(default_shift)

	flags = []
	for shift_type in set(filter(None, shift_types)):
		row = frappe.db.get_value(
			"Shift Type",
			shift_type,
			["allow_employee_checkin_from_mobile_app", "allow_geolocation_tracking"],
			as_dict=True,
		)
		if row:
			flags.append(row)
	return flags


@frappe.whitelist()
def get_hr_settings() -> dict:
	"""Settings the PWA needs at startup.

	Mobile check-in and geolocation tracking are configured per Shift Type, so
	they are resolved from the active employee's shift(s) for today rather than a
	global toggle. No resolvable shift ⇒ both off. When the employee has more
	than one shift today, the flags are OR-ed (any shift that permits it wins);
	per-shift enforcement still happens server-side on the actual check-in."""
	settings = frappe.db.get_singles_dict("HR Settings", cast=True)

	allow_checkin = 0
	allow_geolocation = 0
	employee = get_active_employee_name()
	if employee:
		for flags in _todays_shift_type_flags(employee):
			allow_checkin = allow_checkin or cint(flags.allow_employee_checkin_from_mobile_app)
			allow_geolocation = allow_geolocation or cint(flags.allow_geolocation_tracking)

	return frappe._dict(
		allow_employee_checkin_from_mobile_app=cint(allow_checkin),
		allow_geolocation_tracking=cint(allow_geolocation),
		prevent_self_leave_approval=settings.prevent_self_leave_approval,
	)


# Notifications
@frappe.whitelist()
def get_unread_notifications_count() -> int:
	return frappe.db.count(
		"PWA Notification",
		{"to_user": frappe.session.user, "read": 0},
	)


@frappe.whitelist()
def mark_all_notifications_as_read() -> None:
	frappe.db.set_value(
		"PWA Notification",
		{"to_user": frappe.session.user, "read": 0},
		"read",
		1,
		update_modified=False,
	)


@frappe.whitelist()
def are_push_notifications_enabled() -> bool:
	try:
		return frappe.db.get_single_value("Push Notification Settings", "enable_push_notification_relay")
	except frappe.DoesNotExistError:
		# push notifications are not supported in the current framework version
		return False


# ---------------------------------------------------------------------------
# Native wrapper handshake — used by the Capacitor app's URL-onboarding screen.
# ---------------------------------------------------------------------------
#
# The configurable native shell asks the user for their company's site URL,
# then probes these PUBLIC endpoints to (a) confirm it's a reachable Frappe
# site, and (b) discover which HR app is installed and what PWA route to load.
# Neither returns sensitive data — safe for allow_guest.


@frappe.whitelist(allow_guest=True)
def ping() -> dict:
	"""Cheapest possible 'is this a Frappe site running our app?' probe.
	Returns a tiny constant payload. The wrapper uses a 200 + the expected
	`app` marker to validate the URL the user typed before going further."""
	return {"app": "indian_hrms_compliance", "ok": True}


@frappe.whitelist(allow_guest=True)
def site_capabilities() -> dict:
	"""Lets the native wrapper self-configure against any site.

	Returns the installed HR apps (most-specific first) and the PWA route the
	wrapper should load. The wrapper shows a friendly 'HRMS isn't installed on
	this site' message when `pwa_route` is null instead of a blank WebView.

	Public + value-free: only app names + routes, never employee data.
	"""
	installed = set(frappe.get_installed_apps())

	apps: list[dict] = []
	# Most-specific app first — indian_hrms_compliance extends hrms, so prefer it.
	if "indian_hrms_compliance" in installed:
		apps.append(
			{"key": "indian_hrms_compliance", "label": "HR & Compliance", "route": "/indian_hrms_compliance"}
		)
	elif "hrms" in installed:
		apps.append({"key": "hrms", "label": "HR", "route": "/hrms"})

	pwa_route = apps[0]["route"] if apps else None

	return {
		"site_name": frappe.local.site,
		"app": "indian_hrms_compliance",
		"apps": apps,
		"pwa_route": pwa_route,
		"push_relay_configured": bool(frappe.conf.get("push_relay_server_url")),
	}


# Attendance
@frappe.whitelist()
def get_attendance_calendar_events(from_date: str, to_date: str) -> dict[str, str]:
	employee = get_current_employee()
	holidays = get_holidays_for_calendar(employee, from_date, to_date)
	attendance = get_attendance_for_calendar(employee, from_date, to_date)
	events = {}

	date = getdate(from_date)
	while date_diff(to_date, date) >= 0:
		date_str = date.strftime("%Y-%m-%d")
		if date in attendance:
			events[date_str] = attendance[date]
		elif date in holidays:
			events[date_str] = "Holiday"
		date = add_days(date, 1)

	return events


def get_attendance_for_calendar(employee: str, from_date: str, to_date: str) -> list[dict[str, str]]:
	attendance = frappe.get_all(
		"Attendance",
		{"employee": employee, "attendance_date": ["between", [from_date, to_date]], "docstatus": 1},
		["attendance_date", "status"],
	)
	return {d["attendance_date"]: d["status"] for d in attendance}


def get_holidays_for_calendar(employee: str, from_date: str, to_date: str) -> list[str]:
	if holiday_list := get_holiday_list_for_employee(employee, raise_exception=False):
		return frappe.get_all(
			"Holiday",
			filters={"parent": holiday_list, "holiday_date": ["between", [from_date, to_date]]},
			pluck="holiday_date",
		)

	return []


@frappe.whitelist()
def get_shift_requests(
	employee: str,
	approver_id: str | None = None,
	for_approval: bool = False,
	limit: int | None = None,
) -> list[dict]:
	filters = get_filters("Shift Request", employee, approver_id, for_approval)
	fields = [
		"name",
		"employee",
		"employee_name",
		"shift_type",
		"from_date",
		"to_date",
		"status",
		"approver",
		"docstatus",
		"creation",
	]

	if workflow_state_field := get_workflow_state_field("Shift Request"):
		fields.append(workflow_state_field)

	shift_requests = frappe.get_list(
		"Shift Request",
		fields=fields,
		filters=filters,
		order_by="creation desc",
		limit=limit,
	)

	if workflow_state_field:
		for application in shift_requests:
			application["workflow_state_field"] = workflow_state_field

	return shift_requests


@frappe.whitelist()
def get_attendance_requests(
	employee: str,
	for_approval: bool = False,
	limit: int | None = None,
) -> list[dict]:
	filters = get_filters("Attendance Request", employee, None, for_approval)
	fields = [
		"name",
		"reason",
		"employee",
		"employee_name",
		"from_date",
		"to_date",
		"include_holidays",
		"shift",
		"docstatus",
		"creation",
	]

	# Surface the approval status + approver remark so the PWA can show the
	# employee whether their request is Open / Approved / Rejected / Needs
	# Clarification (and why).
	if frappe.get_meta("Attendance Request").has_field("status"):
		fields += ["status", "rejection_reason", "attachment"]

	if workflow_state_field := get_workflow_state_field("Attendance Request"):
		fields.append(workflow_state_field)

	attendance_requests = frappe.get_list(
		"Attendance Request",
		fields=fields,
		filters=filters,
		order_by="creation desc",
		limit=limit,
	)

	if workflow_state_field:
		for application in attendance_requests:
			application["workflow_state_field"] = workflow_state_field

	return attendance_requests


def get_filters(
	doctype: str,
	employee: str,
	approver_id: str | None = None,
	for_approval: bool = False,
) -> dict:
	filters = frappe._dict()
	if for_approval:
		filters.docstatus = 0
		filters.employee = ("!=", employee)

		if workflow := get_workflow(doctype):
			allowed_states = get_allowed_states_for_workflow(workflow, approver_id)
			filters[workflow.workflow_state_field] = ("in", allowed_states)
		elif doctype == "Attendance Request":
			# Only genuinely-pending requests belong in an approver list — exclude
			# Rejected (terminal) and Needs Clarification (back with the employee).
			if frappe.get_meta("Attendance Request").has_field("status"):
				filters.status = "Open"
		else:
			approver_field_map = {
				"Shift Request": "approver",
				"Leave Application": "leave_approver",
				"Expense Claim": "expense_approver",
			}
			filters.status = "Open" if doctype == "Leave Application" else "Draft"
			if approver_id:
				filters[approver_field_map[doctype]] = approver_id
	else:
		filters.docstatus = ("!=", 2)
		filters.employee = employee

	return filters


@frappe.whitelist()
def get_shift_request_approvers(employee: str) -> str | list[str]:
	shift_request_approver, department = frappe.get_cached_value(
		"Employee",
		employee,
		["shift_request_approver", "department"],
	)
	# Employee-level approver is now an Employee link; resolve to its User.
	shift_request_approver = resolve_employee_approver(shift_request_approver)

	department_approvers = []
	if department:
		department_approvers = get_department_approvers(department, "shift_request_approver")
		if not shift_request_approver:
			shift_request_approver = frappe.db.get_value(
				"Department Approver",
				{"parent": department, "parentfield": "shift_request_approver", "idx": 1},
				"approver",
			)

	shift_request_approver_name = frappe.db.get_value("User", shift_request_approver, "full_name", cache=True)

	if shift_request_approver and shift_request_approver not in [
		approver.name for approver in department_approvers
	]:
		department_approvers.insert(
			0, {"name": shift_request_approver, "full_name": shift_request_approver_name}
		)

	return department_approvers


@frappe.whitelist()
def get_shifts() -> list[dict[str, str]]:
	employee = get_current_employee()
	ShiftAssignment = frappe.qb.DocType("Shift Assignment")
	ShiftType = frappe.qb.DocType("Shift Type")
	return (
		frappe.qb.from_(ShiftAssignment)
		.join(ShiftType)
		.on(ShiftAssignment.shift_type == ShiftType.name)
		.select(
			ShiftAssignment.name,
			ShiftAssignment.shift_type,
			ShiftAssignment.start_date,
			ShiftAssignment.end_date,
			ShiftType.start_time,
			ShiftType.end_time,
		)
		.where(
			(ShiftAssignment.employee == employee)
			& (ShiftAssignment.status == "Active")
			& (ShiftAssignment.docstatus == 1)
		)
		.orderby(ShiftAssignment.start_date, order=Order.asc)
	).run(as_dict=True)


# Leaves and Holidays
@frappe.whitelist()
def get_leave_applications(
	employee: str,
	approver_id: str | None = None,
	for_approval: bool = False,
	limit: int | None = None,
) -> list[dict]:
	filters = get_filters("Leave Application", employee, approver_id, for_approval)
	fields = [
		"name",
		"posting_date",
		"employee",
		"employee_name",
		"leave_type",
		"status",
		"from_date",
		"to_date",
		"half_day",
		"half_day_date",
		"description",
		"total_leave_days",
		"leave_balance",
		"leave_approver",
		"posting_date",
		"creation",
	]

	if workflow_state_field := get_workflow_state_field("Leave Application"):
		fields.append(workflow_state_field)

	applications = frappe.get_list(
		"Leave Application",
		fields=fields,
		filters=filters,
		order_by="posting_date desc",
		limit=limit,
	)

	if workflow_state_field:
		for application in applications:
			application["workflow_state_field"] = workflow_state_field

	return applications


@frappe.whitelist()
def get_leave_balance_map() -> dict[str, dict[str, float]]:
	"""
	Returns a map of leave type and balance details like:
	{
	        'Casual Leave': {'allocated_leaves': 10.0, 'balance_leaves': 5.0},
	        'Earned Leave': {'allocated_leaves': 3.0, 'balance_leaves': 3.0},
	}
	"""
	from indian_hrms_compliance.hr.doctype.leave_application.leave_application import get_leave_details

	employee = get_current_employee()

	date = getdate()
	leave_map = {}

	leave_details = get_leave_details(employee, date)
	allocation = leave_details["leave_allocation"]

	for leave_type, details in allocation.items():
		leave_map[leave_type] = {
			"allocated_leaves": details.get("total_leaves"),
			"balance_leaves": details.get("remaining_leaves"),
		}

	return leave_map


@frappe.whitelist()
def get_holidays_for_employee(employee: str) -> list[dict]:
	holiday_list = get_holiday_list_for_employee(employee, raise_exception=False)
	if not holiday_list:
		return []

	Holiday = frappe.qb.DocType("Holiday")
	holidays = (
		frappe.qb.from_(Holiday)
		.select(Holiday.name, Holiday.holiday_date, Holiday.description)
		.where((Holiday.parent == holiday_list) & (Holiday.weekly_off == 0))
		.orderby(Holiday.holiday_date, order=Order.asc)
	).run(as_dict=True)

	for holiday in holidays:
		holiday["description"] = strip_html(holiday["description"] or "").strip()

	return holidays


@frappe.whitelist()
def get_leave_approval_details(employee: str) -> dict:
	leave_approver, department = frappe.get_cached_value(
		"Employee",
		employee,
		["leave_approver", "department"],
	)
	# Employee-level approver is now an Employee link; resolve to its User.
	leave_approver = resolve_employee_approver(leave_approver)

	if not leave_approver and department:
		leave_approver = frappe.db.get_value(
			"Department Approver",
			{"parent": department, "parentfield": "leave_approvers", "idx": 1},
			"approver",
		)

	leave_approver_name = frappe.db.get_value("User", leave_approver, "full_name", cache=True)
	department_approvers = get_department_approvers(department, "leave_approvers")

	if leave_approver and leave_approver not in [approver.name for approver in department_approvers]:
		department_approvers.append({"name": leave_approver, "full_name": leave_approver_name})

	return dict(
		leave_approver=leave_approver,
		leave_approver_name=leave_approver_name,
		department_approvers=department_approvers,
		is_mandatory=frappe.db.get_single_value(
			"HR Settings", "leave_approver_mandatory_in_leave_application"
		),
	)


def get_department_approvers(department: str, parentfield: str) -> list[str]:
	if not department:
		return []

	department_details = frappe.db.get_value("Department", department, ["lft", "rgt"], as_dict=True)
	departments = frappe.get_all(
		"Department",
		filters={
			"lft": ("<=", department_details.lft),
			"rgt": (">=", department_details.rgt),
			"disabled": 0,
		},
		pluck="name",
	)

	Approver = frappe.qb.DocType("Department Approver")
	User = frappe.qb.DocType("User")
	department_approvers = (
		frappe.qb.from_(User)
		.join(Approver)
		.on(Approver.approver == User.name)
		.select(User.name.as_("name"), User.full_name.as_("full_name"))
		.where((Approver.parent.isin(departments)) & (Approver.parentfield == parentfield))
	).run(as_dict=True)

	return department_approvers


@frappe.whitelist()
def get_leave_types(employee: str, date: str) -> list:
	from indian_hrms_compliance.hr.doctype.leave_application.leave_application import get_leave_details

	date = date or getdate()

	leave_details = get_leave_details(employee, date)
	leave_types = list(leave_details["leave_allocation"].keys()) + leave_details["lwps"]

	return leave_types


# Expense Claims
@frappe.whitelist()
def get_expense_claims(
	employee: str,
	approver_id: str | None = None,
	for_approval: bool = False,
	limit: int | None = None,
) -> list[dict]:
	filters = get_filters("Expense Claim", employee, approver_id, for_approval)
	fields = [
		"`tabExpense Claim`.name",
		"`tabExpense Claim`.posting_date",
		"`tabExpense Claim`.employee",
		"`tabExpense Claim`.employee_name",
		"`tabExpense Claim`.approval_status",
		"`tabExpense Claim`.status",
		"`tabExpense Claim`.expense_approver",
		"`tabExpense Claim`.total_claimed_amount",
		"`tabExpense Claim`.posting_date",
		"`tabExpense Claim`.company",
		"`tabExpense Claim`.creation",
		"`tabExpense Claim Detail`.expense_type",
		"count(`tabExpense Claim Detail`.expense_type) as total_expenses",
	]

	if workflow_state_field := get_workflow_state_field("Expense Claim"):
		fields.append(workflow_state_field)

	claims = frappe.get_list(
		"Expense Claim",
		fields=fields,
		filters=filters,
		order_by="`tabExpense Claim`.posting_date desc",
		group_by="`tabExpense Claim`.name",
		limit=limit,
	)

	if workflow_state_field:
		for claim in claims:
			claim["workflow_state_field"] = workflow_state_field

	return claims


@frappe.whitelist()
def get_expense_claim_summary() -> dict:
	employee = get_current_employee()

	from frappe.query_builder.functions import Sum

	Claim = frappe.qb.DocType("Expense Claim")

	pending_claims_case = (
		frappe.qb.terms.Case().when(Claim.approval_status == "Draft", Claim.total_claimed_amount).else_(0)
	)
	sum_pending_claims = Sum(pending_claims_case).as_("total_pending_amount")

	approved_claims_case = (
		frappe.qb.terms.Case()
		.when(Claim.approval_status == "Approved", Claim.total_sanctioned_amount)
		.else_(0)
	)
	sum_approved_claims = Sum(approved_claims_case).as_("total_approved_amount")

	approved_total_claimed_case = (
		frappe.qb.terms.Case().when(Claim.approval_status == "Approved", Claim.total_claimed_amount).else_(0)
	)
	sum_approved_total_claimed = Sum(approved_total_claimed_case).as_("total_claimed_in_approved")

	rejected_claims_case = (
		frappe.qb.terms.Case().when(Claim.approval_status == "Rejected", Claim.total_claimed_amount).else_(0)
	)
	sum_rejected_claims = Sum(rejected_claims_case).as_("total_rejected_amount")

	summary = (
		frappe.qb.from_(Claim)
		.select(
			sum_pending_claims,
			sum_approved_claims,
			sum_rejected_claims,
			sum_approved_total_claimed,
			Claim.company,
		)
		.where((Claim.docstatus != 2) & (Claim.employee == employee))
	).run(as_dict=True)[0]

	currency = frappe.db.get_value("Company", summary.company, "default_currency")
	summary["currency"] = currency

	return summary


@frappe.whitelist()
def get_expense_type_description(expense_type: str) -> str:
	return frappe.db.get_value("Expense Claim Type", expense_type, "description")


@frappe.whitelist()
def get_expense_claim_types() -> list[dict]:
	ClaimType = frappe.qb.DocType("Expense Claim Type")

	return (frappe.qb.from_(ClaimType).select(ClaimType.name, ClaimType.description)).run(as_dict=True)


@frappe.whitelist()
def get_expense_approval_details(employee: str) -> dict:
	expense_approver, department = frappe.get_cached_value(
		"Employee",
		employee,
		["expense_approver", "department"],
	)
	# Employee-level approver is now an Employee link; resolve to its User.
	expense_approver = resolve_employee_approver(expense_approver)

	if not expense_approver and department:
		expense_approver = frappe.db.get_value(
			"Department Approver",
			{"parent": department, "parentfield": "expense_approvers", "idx": 1},
			"approver",
		)

	expense_approver_name = frappe.db.get_value("User", expense_approver, "full_name", cache=True)
	department_approvers = get_department_approvers(department, "expense_approvers")

	if expense_approver and expense_approver not in [approver.name for approver in department_approvers]:
		department_approvers.append({"name": expense_approver, "full_name": expense_approver_name})

	return dict(
		expense_approver=expense_approver,
		expense_approver_name=expense_approver_name,
		department_approvers=department_approvers,
		is_mandatory=frappe.db.get_single_value("HR Settings", "expense_approver_mandatory_in_expense_claim"),
	)


# Employee Advance
@frappe.whitelist()
def get_employee_advance_balance() -> list[dict]:
	employee = get_current_employee()
	Advance = frappe.qb.DocType("Employee Advance")

	advances = (
		frappe.qb.from_(Advance)
		.select(
			Advance.name,
			Advance.employee,
			Advance.status,
			Advance.purpose,
			Advance.paid_amount,
			(Advance.paid_amount - (Advance.claimed_amount + Advance.return_amount)).as_("balance_amount"),
			Advance.posting_date,
			Advance.currency,
		)
		.where(
			(Advance.docstatus == 1)
			& (Advance.paid_amount)
			& (Advance.employee == employee)
			# don't need claimed & returned advances, only partly or completely paid ones
			& (Advance.status.isin(["Paid", "Unpaid"]))
		)
		.orderby(Advance.posting_date, order=Order.desc)
	).run(as_dict=True)

	return advances


@frappe.whitelist()
def get_advance_account(company: str) -> str | None:
	return frappe.db.get_value("Company", company, "default_employee_advance_account", cache=True)


# Company
@frappe.whitelist()
def get_company_currencies() -> dict:
	Company = frappe.qb.DocType("Company")
	Currency = frappe.qb.DocType("Currency")

	query = (
		frappe.qb.from_(Company)
		.join(Currency)
		.on(Company.default_currency == Currency.name)
		.select(
			Company.name,
			Company.default_currency,
			Currency.name.as_("currency"),
			Currency.symbol.as_("symbol"),
		)
	)

	companies = query.run(as_dict=True)
	return {company.name: (company.default_currency, company.symbol) for company in companies}


@frappe.whitelist()
def get_currency_symbols() -> dict:
	Currency = frappe.qb.DocType("Currency")

	currencies = (frappe.qb.from_(Currency).select(Currency.name, Currency.symbol)).run(as_dict=True)

	return {currency.name: currency.symbol or currency.name for currency in currencies}


@frappe.whitelist()
def get_company_cost_center_and_expense_account(company: str) -> dict:
	return frappe.db.get_value(
		"Company", company, ["cost_center", "default_expense_claim_payable_account"], as_dict=True
	)


# Form View APIs
@frappe.whitelist()
def get_doctype_fields(doctype: str) -> list[dict]:
	fields = frappe.get_meta(doctype).fields
	return [
		field
		for field in fields
		if field.fieldtype in SUPPORTED_FIELD_TYPES and field.fieldname != "amended_from"
	]


@frappe.whitelist()
def get_doctype_states(doctype: str) -> dict:
	states = frappe.get_meta(doctype).states
	return {state.title: state.color.lower() for state in states}


# File
@frappe.whitelist()
def get_attachments(dt: str, dn: str):
	return frappe.get_list(
		"File",
		fields=["name", "file_name", "file_url", "is_private"],
		filters={"attached_to_name": str(dn), "attached_to_doctype": dt},
	)


@frappe.whitelist()
def upload_base64_file(content, filename, dt=None, dn=None, fieldname=None):
	import base64
	import io
	from mimetypes import guess_type

	from PIL import Image, ImageOps

	from frappe.handler import ALLOWED_MIMETYPES

	decoded_content = base64.b64decode(content)
	content_type = guess_type(filename)[0]
	if content_type not in ALLOWED_MIMETYPES:
		frappe.throw(_("You can only upload JPG, PNG, PDF, TXT or Microsoft documents."))

	if content_type.startswith("image/jpeg"):
		# transpose the image according to the orientation tag, and remove the orientation data
		with Image.open(io.BytesIO(decoded_content)) as image:
			transpose_img = ImageOps.exif_transpose(image)
			# convert the image back to bytes
			file_content = io.BytesIO()
			transpose_img.save(file_content, format="JPEG")
			file_content = file_content.getvalue()
	else:
		file_content = decoded_content

	return frappe.get_doc(
		{
			"doctype": "File",
			"attached_to_doctype": dt,
			"attached_to_name": dn,
			"attached_to_field": fieldname,
			"folder": "Home",
			"file_name": filename,
			"content": file_content,
			"is_private": 1,
		}
	).insert()


@frappe.whitelist()
def delete_attachment(filename: str):
	frappe.delete_doc("File", filename)


@frappe.whitelist()
def download_salary_slip(name: str):
	"""Stream the Salary Slip PDF as a binary download. download_pdf sets
	frappe.local.response (filename/filecontent/type='pdf'); returning None lets
	Frappe serve the raw PDF so the PWA's response.blob() gets actual bytes (a
	base64/JSON wrapper produced a broken .crdownload)."""
	from frappe.utils.print_format import download_pdf

	# Use the elegant format unless an explicit non-Standard default is configured.
	print_format = frappe.get_meta("Salary Slip").default_print_format
	if not print_format or print_format == "Standard":
		print_format = "Salary Slip Elegant"

	try:
		download_pdf("Salary Slip", name, format=print_format)
	except Exception:
		frappe.log_error(title="Salary Slip PDF download failed", message=frappe.get_traceback())
		frappe.throw(_("Failed to download Salary Slip PDF. See Error Log (often the site host_name / wkhtmltopdf)."))

	# Force a real attachment download (download_pdf serves 'inline', which some
	# browsers open in-tab); type 'download' sets Content-Disposition: attachment.
	frappe.local.response.type = "download"


# Workflow
@frappe.whitelist()
def get_workflow(doctype: str) -> dict:
	workflow = get_workflow_name(doctype)
	if not workflow:
		return frappe._dict()
	return frappe.get_doc("Workflow", workflow)


def get_workflow_state_field(doctype: str) -> str | None:
	workflow_name = get_workflow_name(doctype)
	if not workflow_name:
		return None

	override_status, workflow_state_field = frappe.db.get_value(
		"Workflow",
		workflow_name,
		["override_status", "workflow_state_field"],
	)
	# NOTE: checkbox labelled 'Don't Override Status' is named override_status hence the inverted logic
	if not override_status:
		return workflow_state_field
	return None


def get_allowed_states_for_workflow(workflow: dict, user_id: str) -> list[str]:
	user_roles = frappe.get_roles(user_id)
	return [transition.state for transition in workflow.transitions if transition.allowed in user_roles]


# Permissions
@frappe.whitelist()
def get_permitted_fields_for_write(doctype: str) -> list[str]:
	return get_permitted_fields(doctype, permission_type="write")


# Policy Acknowledgement (Phase 7B — surfaced in the ESS PWA)
def _get_policy_acknowledgements(status: str) -> list[dict]:
	"""Employee Policy Acknowledgements for the active Employee in the given
	status, joined with the HRMS Policy content. Employee-scoped so it
	refetches the right employment when the user switches employer."""
	employee = get_current_employee()
	acknowledgements = frappe.get_list(
		"Employee Policy Acknowledgement",
		filters={"employee": employee, "status": status},
		fields=[
			"name",
			"employee",
			"company",
			"policy",
			"policy_name_fetched",
			"policy_version",
			"policy_category",
			"due_date",
			"signed_text",
			"status",
			"acknowledged_at",
		],
		order_by="due_date asc",
	)

	for ack in acknowledgements:
		content = frappe.db.get_value(
			"HRMS Policy",
			ack.policy,
			["content_html", "attachment", "effective_date"],
			as_dict=True,
		)
		if content:
			ack["content_html"] = content.content_html
			ack["attachment"] = content.attachment
			ack["effective_date"] = content.effective_date

	return acknowledgements


@frappe.whitelist()
def get_pending_policy_acknowledgements() -> list[dict]:
	"""Pending policies awaiting acknowledgement by the active Employee."""
	return _get_policy_acknowledgements("Pending")


@frappe.whitelist()
def get_acknowledged_policies() -> list[dict]:
	"""Already-acknowledged policies for the active Employee (history tab)."""
	return _get_policy_acknowledgements("Acknowledged")


@frappe.whitelist()
def acknowledge_policy(acknowledgement_name: str) -> dict:
	"""The active Employee acknowledges one of their pending policies.

	Validates the acknowledgement belongs to the current employee before
	marking it Acknowledged (via PWA). Throws if not owned."""
	employee = get_current_employee()
	ack = frappe.get_doc("Employee Policy Acknowledgement", acknowledgement_name)
	if ack.employee != employee:
		frappe.throw(
			_("You are not permitted to acknowledge this policy."),
			frappe.PermissionError,
		)
	ack.acknowledge(via="PWA")
	return {
		"name": ack.name,
		"status": ack.status,
		"acknowledged_at": str(ack.acknowledged_at),
	}


# My Tasks (Phase 7B — surfaced in the ESS PWA)
TASK_INSTANCE_FIELDS = [
	"name",
	"goal_name",
	"kra",
	"task_template",
	"period_label",
	"due_date",
	"status",
	"completion_type",
	"numeric_value",
	"task_notes",
	"task_attachment",
	"approver_user",
	"delegated_from",
	"performed_by",
	"accountable_parent",
	# Approval cycle — lets the PWA distinguish "awaiting approval" from "sent
	# back", and show the approver's reason instead of a bare status.
	"submitted_at",
	"approved_by",
	"approved_at",
	"approval_notes",
	# Audit / dashboard:
	"owner",          # the user who created the Goal — used to identify the
	                  # assigner for ad-hoc tasks (also drives overdue alerts).
	"creation",
]

# Template attributes the PWA needs per instance. Fetched once per template.
_TEMPLATE_META_FIELDS = ("requires_approval", "risk_tier", "playbook", "assign_to_head")


def _annotate_template_meta(tasks: list[dict]) -> None:
	"""Copy the parent HRMS Task's requires_approval + risk_tier onto each row.

	One lookup per distinct template, not per row. Ad-hoc instances (no
	template) are flagged and treated as Routine — a one-off task someone typed
	in carries no ceremony by definition.
	"""
	cache: dict[str, dict] = {}
	name_cache: dict[str, str] = {}
	for t in tasks:
		template = t.get("task_template")
		if template and template not in cache:
			cache[template] = (
				frappe.db.get_value(
					"HRMS Task", template, _TEMPLATE_META_FIELDS, as_dict=True
				)
				or {}
			)
		meta = cache.get(template) or {}
		t["requires_approval"] = meta.get("requires_approval") or 0
		t["risk_tier"] = meta.get("risk_tier") or "Routine"
		t["playbook"] = meta.get("playbook") or None
		t["is_adhoc"] = 1 if not template else 0
		# Distribution (Assign-to-Head): a top Accountable instance can be split
		# to reports; a child (has accountable_parent) can be bounced back.
		t["is_distributed_child"] = 1 if t.get("accountable_parent") else 0
		t["can_distribute"] = (
			1 if (meta.get("assign_to_head") and not t.get("accountable_parent")) else 0
		)
		# Derived UI state, so every screen agrees on what "pending" means.
		t["awaiting_approval"] = 1 if (t.get("submitted_at") and t.get("status") == "In Progress") else 0
		t["was_sent_back"] = (
			1 if (t.get("approval_notes") and not t.get("submitted_at") and not t.get("approved_at")) else 0
		)
		# "Approved by priya@acme.com" reads like a system log; show the person.
		# One lookup per distinct approver, not per row.
		if approver := t.get("approved_by"):
			if approver not in name_cache:
				name_cache[approver] = (
					frappe.db.get_value("User", approver, "full_name", cache=True) or approver
				)
			t["approved_by_name"] = name_cache[approver]

	# One bulk query: which distributable instances have ALREADY been distributed
	# (have children), so the PWA shows "awaiting reports" instead of "Distribute".
	distributable = [t["name"] for t in tasks if t.get("can_distribute")]
	if distributable and frappe.get_meta("Goal").has_field("accountable_parent"):
		with_children = set(
			frappe.get_all(
				"Goal",
				filters={"accountable_parent": ("in", distributable)},
				pluck="accountable_parent",
			)
		)
		for t in tasks:
			t["has_distributed_children"] = 1 if t["name"] in with_children else 0


@frappe.whitelist()
def get_my_task_instances(status_filter: str | None = None, period: str | None = None) -> list[dict]:
	"""Task Instances (Goal rows with goal_type='Task Instance') for the active
	Employee. Optionally narrowed by status, or by a due-date window:
	  - 'today'    : due today
	  - 'overdue'  : due before today and not yet Completed/Archived/Closed
	  - 'upcoming' : due after today and not yet Completed/Archived/Closed
	  - 'completed': status Completed
	"""
	employee = get_current_employee()
	filters = frappe._dict({"goal_type": "Task Instance", "employee": employee})
	today_d = getdate()

	if status_filter:
		filters.status = status_filter

	if period == "today":
		filters.due_date = today_d
	elif period == "overdue":
		filters.due_date = ("<", today_d)
		filters.status = ("in", ["Pending", "In Progress"])
	elif period == "upcoming":
		filters.due_date = (">", today_d)
		filters.status = ("in", ["Pending", "In Progress"])
	elif period == "completed":
		filters.status = "Completed"

	tasks = frappe.get_list(
		"Goal",
		filters=filters,
		fields=TASK_INSTANCE_FIELDS,
		order_by="due_date asc",
	)
	_annotate_template_meta(tasks)
	return tasks


@frappe.whitelist()
def get_my_scorecard() -> list[dict]:
	"""The current employee's KPI scorecard: the latest snapshot per measured
	task, with a short trend (recent periods) for a sparkline. Live between
	appraisals — driven by the weekly KPI Snapshot rollup.
	"""
	if not frappe.db.table_exists("KPI Snapshot"):
		return []
	employee = get_current_employee()
	# Dial 2: the KPI scorecard is a Growth+ surface. A Startup-profile company
	# stays lean — no scorecard ceremony.
	from indian_hrms_compliance.api.governance import profile_at_least

	company = frappe.db.get_value("Employee", employee, "company")
	if not profile_at_least(company, "Growth"):
		return []
	rows = frappe.get_all(
		"KPI Snapshot",
		filters={"employee": employee},
		fields=[
			"task_template",
			"task_name",
			"kra",
			"period_label",
			"snapshot_date",
			"target_value",
			"actual_value",
			"achievement_pct",
			"measurement_unit",
			"rollup_method",
		],
		# Tie-break: a whole run shares snapshot_date=today, so add creation to
		# keep "latest per task" and the trend order deterministic.
		order_by="snapshot_date desc, creation desc",
	)
	by_task: dict[str, dict] = {}
	for r in rows:
		card = by_task.get(r.task_template)
		if card is None:
			by_task[r.task_template] = {
				"task_template": r.task_template,
				"task_name": r.task_name,
				"kra": r.kra,
				"period_label": r.period_label,
				"target_value": r.target_value,
				"actual_value": r.actual_value,
				"achievement_pct": r.achievement_pct,
				"measurement_unit": r.measurement_unit,
				"rollup_method": r.rollup_method,
				"trend": [],
			}
			card = by_task[r.task_template]
		# Oldest→newest trend, capped, for a sparkline.
		if len(card["trend"]) < 8:
			card["trend"].insert(0, r.achievement_pct)
	return list(by_task.values())


@frappe.whitelist()
def get_my_tasks_dashboard() -> dict:
	"""Single-call payload for the My Tasks PWA screen — five partitioned
	buckets so the front-end doesn't have to make round-trips per tab:

	  - today           : OPEN recurring tasks (with a template) due today
	  - adhoc           : OPEN ad-hoc tasks (no template), regardless of due
	                      date, not yet overdue — these are "do soon" work
	  - upcoming        : OPEN recurring tasks due tomorrow or later
	  - overdue         : OPEN tasks (any kind) past due
	  - completed_week  : status=Completed, modified within the current ISO week

	An ad-hoc task that's been overdue counts only in `overdue`, not `adhoc`,
	so users see one item exactly once per screen view. Recurring tasks bucket
	by due date the way they always did.
	"""
	employee = get_current_employee()
	today_d = getdate()
	week_start = add_days(today_d, -getdate(today_d).weekday())
	open_states = ["Pending", "In Progress"]

	def _list(extra: dict) -> list[dict]:
		filters = {"goal_type": "Task Instance", "employee": employee, **extra}
		rows = frappe.get_list("Goal", filters=filters, fields=TASK_INSTANCE_FIELDS, order_by="due_date asc")
		_annotate_template_meta(rows)
		return rows

	today_tasks = _list(
		{"status": ("in", open_states), "due_date": today_d, "task_template": ("is", "set")}
	)
	upcoming_tasks = _list(
		{"status": ("in", open_states), "due_date": (">", today_d), "task_template": ("is", "set")}
	)
	adhoc_tasks = _list(
		{
			"status": ("in", open_states),
			"task_template": ("is", "not set"),
			"due_date": (">=", today_d),
		}
	)
	overdue_tasks = _list({"status": ("in", open_states), "due_date": ("<", today_d)})
	completed_week = _list({"status": "Completed", "modified": (">=", week_start)})

	summary = {
		"due_today": len(today_tasks) + sum(1 for t in adhoc_tasks if t.get("due_date") == today_d),
		"adhoc_open": len(adhoc_tasks),
		"overdue": len(overdue_tasks),
		"completed_this_week": len(completed_week),
	}

	return {
		"summary": summary,
		"today": today_tasks,
		"adhoc": adhoc_tasks,
		"upcoming": upcoming_tasks,
		"overdue": overdue_tasks,
		"completed_week": completed_week,
	}


@frappe.whitelist()
def get_my_task_summary() -> dict:
	"""Counts for the Tasks dashboard cards (active Employee scope)."""
	employee = get_current_employee()
	today_d = getdate()
	week_start = add_days(today_d, -getdate(today_d).weekday())

	Goal = frappe.qb.DocType("Goal")
	base = (Goal.goal_type == "Task Instance") & (Goal.employee == employee)
	open_states = ["Pending", "In Progress"]

	def _count(condition) -> int:
		return (
			frappe.qb.from_(Goal).select(frappe.qb.terms.PseudoColumn("COUNT(*)")).where(base & condition)
		).run()[0][0]

	return {
		"due_today": _count((Goal.due_date == today_d) & (Goal.status.isin(open_states))),
		"overdue": _count((Goal.due_date < today_d) & (Goal.status.isin(open_states))),
		"completed_this_week": _count(
			(Goal.status == "Completed") & (Goal.modified >= week_start)
		),
		"pending": _count(Goal.status.isin(open_states)),
	}


@frappe.whitelist()
def complete_task_instance(
	goal_name: str,
	numeric_value: float | None = None,
	notes: str | None = None,
	attachment: str | None = None,
	performed_by: str | None = None,
) -> dict:
	"""The active Employee completes one of their Task Instances.

	Validates ownership, records numeric_value/notes/attachment when supplied,
	stamps the submission, and sets status: tasks whose template requires
	approval move to 'In Progress' (pending approval); others go to 'Completed'.

	Leave cover: a task delegated to the reporting manager (``delegated_from``
	set) requires ``performed_by`` — the manager records who actually did it.
	"""
	employee = get_current_employee()
	goal = frappe.get_doc("Goal", goal_name)
	if goal.goal_type != "Task Instance" or goal.employee != employee:
		frappe.throw(
			_("You are not permitted to complete this task."),
			frappe.PermissionError,
		)

	# Re-submitting an already-approved instance would silently wipe the
	# approver's signature below (the approval stamps are cleared to start a
	# fresh cycle) and push accepted work back into the queue. That is the same
	# erasure `reopen_task_instance` refuses — it must not be reachable through
	# the front door either. Re-opening is the approver's / HR's call.
	if goal.get("approved_by"):
		frappe.throw(
			_("This task has already been approved and cannot be submitted again."),
			frappe.PermissionError,
		)

	# A distributed Accountable instance with OPEN children can't be ticked done
	# directly — it auto-completes when every child finishes (the head does it
	# solo only if they never distributed it).
	if _has_open_children(goal.name):
		frappe.throw(
			_(
				"This task has been distributed to your reports. It completes automatically "
				"when they finish — you can't mark it done directly."
			),
			frappe.PermissionError,
		)

	# Leave-cover delegation (delegated_from, no accountable_parent) asks the cover
	# manager WHO actually did it. A distributed child also carries delegated_from
	# for lineage, but there the assignee IS the performer — so don't demand it.
	if goal.get("delegated_from") and not goal.get("accountable_parent"):
		if not performed_by:
			frappe.throw(_("This task was delegated to you for leave cover. Please record who performed it."))
		goal.performed_by = performed_by

	if numeric_value is not None:
		goal.numeric_value = numeric_value
	if notes is not None:
		goal.task_notes = notes
	if attachment is not None:
		goal.task_attachment = attachment

	requires_approval = 0
	if goal.task_template:
		requires_approval = frappe.db.get_value("HRMS Task", goal.task_template, "requires_approval") or 0

	goal.submitted_at = frappe.utils.now()
	goal.submitted_by = frappe.session.user
	# A re-submission starts a fresh approval cycle: drop the previous decision
	# so a stale "sent back" note can't be mistaken for this attempt's verdict.
	for field in ("approved_by", "approved_at", "approval_notes"):
		if goal.meta.has_field(field):
			goal.set(field, None)
	# Goal.validate() derives status from progress via set_status(); set both so the
	# intended state survives. Approval-gated tasks sit at 'In Progress' (pending
	# the approver); others complete outright at progress=100.
	if requires_approval:
		goal.status = "In Progress"
		if not flt(goal.progress):
			goal.progress = 99
	else:
		goal.status = "Completed"
		goal.progress = 100

	goal.flags.ihc_governed_write = True
	goal.save(ignore_permissions=True)

	# If this was a distributed child and it (and its siblings) are now done, the
	# head's Accountable parent rolls up to complete automatically.
	if goal.get("accountable_parent") and goal.status == "Completed":
		_maybe_complete_accountable_parent(goal.accountable_parent)

	# Live-refresh the employee's screens AND, if approval is required, whoever
	# now has to review it — a named approver, every holder of the approver role,
	# or (when it routed to nobody) HR, who acts as the backstop.
	_pwa_refetch(
		list(_REQUESTER_CACHE_KEYS_BY_DOCTYPE["Goal"]), user=frappe.session.user
	)
	if requires_approval:
		for user in _task_approver_audience(goal):
			_pwa_refetch(list(_INBOX_CACHE_KEYS), user=user)

	return {"name": goal.name, "status": goal.status, "requires_approval": bool(requires_approval)}


def _dedupe_users(users, exclude: set[str]) -> list[str]:
	"""Order-preserving de-dupe, minus the excluded users and Guest.

	Administrator is deliberately NOT excluded. `task_owner` defaults to
	`__user`, so any task authored while logged in as Administrator resolves its
	approver to Administrator — treating that as "nobody" would declare a large
	share of a freshly-provisioned site's tasks stranded and dump them all into
	HR's backstop queue while they simultaneously sit, correctly routed, in
	Administrator's own inbox.
	"""
	seen: set[str] = set()
	out = []
	for u in users:
		if u and u not in seen and u not in exclude and u != "Guest":
			seen.add(u)
			out.append(u)
	return out


def _enabled_users(users) -> set[str]:
	"""Of `users`, the ones whose User account is still enabled.

	A disabled account cannot act, so routing to one is the same as routing
	nowhere — the instance must fall through to the HR backstop rather than rot
	in a dead inbox. This is the "nothing dies with one person's account"
	guarantee the role-routing docstring promises.
	"""
	names = {u for u in users if u}
	if not names:
		return set()
	return set(
		frappe.get_all("User", filters={"name": ("in", list(names)), "enabled": 1}, pluck="name")
	)


# One task's approver role, capped + ordered the same way on the single-row and
# bulk paths so they never disagree about whether a many-holder role is stranded.
_ROLE_HOLDER_CAP = 50


def _task_routed_approvers(doc, limit: int = _ROLE_HOLDER_CAP, doers: set[str] | None = None) -> list[str]:
	"""Non-doer users this instance is explicitly ROUTED to.

	An EMPTY result means the instance is effectively unrouted and HR must step
	in. That covers three cases, not just a blank approver:

	  * no approver_user and no approver_role at all;
	  * an approver_role nobody holds (or held only by the doer);
	  * an approver_user who IS the doer — which is what leave-cover
	    delegation produces, since it moves `employee` to the reporting manager
	    while `approver_user` still points at that same manager. Without this,
	    the instance would sit forever in the one inbox whose owner the
	    segregation-of-duties gate forbids from approving it.

	`doers` may be passed in when the caller has already resolved them, so a list
	view doesn't re-query Employee → user_id for every row.
	"""
	doers = _task_doer_users(doc) if doers is None else doers
	users = _dedupe_users([doc.get("approver_user")], doers)
	# Fall through to the role when the named approver is unusable (the doer, or
	# an emptied field) — the two routes are independent, so a task carrying both
	# must not be declared stranded just because the named user dropped out.
	if not users and doc.get("approver_role"):
		users = _dedupe_users(
			frappe.get_all(
				"Has Role",
				filters={"role": doc.approver_role, "parenttype": "User"},
				pluck="parent",
				order_by="parent asc",
				limit=limit,
			),
			doers,
		)
	enabled = _enabled_users(users)
	return [u for u in users if u in enabled]


def _hr_backstop_users(doc, limit: int = 20) -> list[str]:
	"""HR users who act as the approver of last resort for a stranded instance.

	Uses the SAME role set as `_is_hr_user` / `_assert_task_approver`, so whoever
	is ALLOWED to approve an unrouted task is also told one is waiting. (These
	previously disagreed — the inbox admitted all HR roles while the live refresh
	only pinged "HR Manager" holders, so an HR User saw nothing until a manual
	reload.)
	"""
	users = _dedupe_users(
		frappe.get_all(
			"Has Role",
			filters={"role": ("in", tuple(_HR_APPROVER_ROLES)), "parenttype": "User"},
			pluck="parent",
			limit=limit,
		),
		_task_doer_users(doc),
	)
	enabled = _enabled_users(users)
	return [u for u in users if u in enabled]


# Ceiling on the HR "stranded" sweep. It reads instances the user was not named
# on, so it must never become an unbounded whole-site scan on a busy morning.
_STRANDED_SWEEP_LIMIT = 200


def _bulk_doer_users(rows) -> dict[str, set[str]]:
	"""`_task_doer_users` for many rows, in ONE Employee query instead of 2 per row."""
	emp_names = {
		r.get(f) for r in rows for f in ("employee", "performed_by") if r.get(f)
	}
	emp_user: dict[str, str] = {}
	if emp_names:
		emp_user = {
			e.name: e.user_id
			for e in frappe.get_all(
				"Employee", filters={"name": ("in", list(emp_names))}, fields=["name", "user_id"]
			)
			if e.user_id
		}
	out: dict[str, set[str]] = {}
	for r in rows:
		users = {r.get("submitted_by")} if r.get("submitted_by") else set()
		for f in ("employee", "performed_by"):
			if user_id := emp_user.get(r.get(f)):
				users.add(user_id)
		out[r.name] = users
	return out


def _bulk_role_holders(roles) -> dict[str, list[str]]:
	"""Holders of several roles at once, keyed by role.

	Each role is capped and ordered identically to the single-row
	`_task_routed_approvers` path, so the inbox (which uses this) and the
	live-refresh audience (which uses that) never disagree on whether a
	many-holder role is stranded."""
	names = {r for r in roles if r}
	if not names:
		return {}
	out: dict[str, list[str]] = {}
	for row in frappe.get_all(
		"Has Role",
		filters={"role": ("in", list(names)), "parenttype": "User"},
		fields=["role", "parent"],
		order_by="parent asc",
	):
		holders = out.setdefault(row.role, [])
		if len(holders) < _ROLE_HOLDER_CAP:
			holders.append(row.parent)
	return out


def _routed_from_maps(row, doers: set[str], role_holders: dict[str, list[str]], enabled: set[str]):
	"""`_task_routed_approvers` for a pre-resolved row — no queries. Same rules."""
	users = _dedupe_users([row.get("approver_user")], doers)
	if not users and row.get("approver_role"):
		users = _dedupe_users(role_holders.get(row.get("approver_role"), []), doers)
	return [u for u in users if u in enabled]


def _task_approver_audience(goal, limit: int = 20) -> list[str]:
	"""Users who should see this submitted instance in their approvals inbox.

	Mirrors the routes in `_pending_task_approvals`. Capped because a role (or
	the HR backstop) can fan out widely and this only drives a UI refresh.
	The doer is always excluded — they are never their own approver.
	"""
	return _task_routed_approvers(goal, limit) or _hr_backstop_users(goal, limit)


def _broadcast_task_decision(goal) -> None:
	"""After a task decision, refresh the inbox of everyone who could have acted
	on it, so the row drops out of the OTHER reviewers' cached lists too.

	The decision cleared/stamped the fields the audience is derived from, so the
	audience is computed against the doc's PRE-decision routing where possible;
	in practice `_task_approver_audience` still resolves the routed approver /
	role / HR backstop from the surviving approver_user / approver_role, which is
	exactly the set that had it queued."""
	for reviewer in _task_approver_audience(goal):
		_pwa_refetch(list(_INBOX_CACHE_KEYS), user=reviewer)


@frappe.whitelist()
def reopen_task_instance(goal_name: str) -> dict:
	"""Re-open a Task Instance completed by mistake — set it back to Pending and
	clear the completion stamps/progress.

	Normally only the owning employee may reopen their own instance. Once an
	approver has signed it off, that flips: re-opening would erase someone else's
	signature (the stamps are cleared below) with no trace and no notice, and
	would let the doer churn reopen → redo → re-route after the work was already
	accepted. So an APPROVED instance can only be re-opened by the approver who
	signed it or by HR — which also means those two must be able to get past the
	owning-employee check, or the "ask them to re-open it" advice would be a lie.
	"""
	goal = frappe.get_doc("Goal", goal_name)
	user = frappe.session.user
	if goal.goal_type != "Task Instance":
		frappe.throw(_("You are not permitted to reopen this task."), frappe.PermissionError)

	approved_by = goal.get("approved_by")
	# Whoever signed it off, and HR, may undo an approval — they do not need to
	# be the owning employee (they never are). But the doer may NEVER undo the
	# approval of their own work, even holding an HR role: that is the same
	# segregation of duties `_assert_task_approver` enforces with no exception,
	# and without excluding doers here an HR-hatted employee could wipe the
	# sign-off on their own task and force a re-run.
	may_undo_approval = (
		bool(approved_by)
		and (approved_by == user or _is_hr_user(user))
		and user not in _task_doer_users(goal)
	)

	if not may_undo_approval:
		if goal.employee != get_current_employee():
			frappe.throw(_("You are not permitted to reopen this task."), frappe.PermissionError)
		if approved_by:
			frappe.throw(
				_(
					"This task has already been approved by {0} and cannot be re-opened by you. "
					"Ask them or HR to re-open it."
				).format(approved_by),
				frappe.PermissionError,
			)

	if goal.status == "Archived":
		frappe.throw(_("Archived tasks cannot be reopened."))

	# Did this instance actually sit in an approver's queue? Only then is there an
	# approver inbox to refresh. A Routine task (no approval) never did, so the
	# common "un-tick a checkbox" reopen must NOT fan a refetch out to all of HR.
	# Captured before the stamps are cleared below.
	was_in_approval_queue = bool(approved_by) or (
		goal.get("submitted_at")
		and goal.task_template
		and frappe.db.get_value("HRMS Task", goal.task_template, "requires_approval")
	)

	goal.status = "Pending"
	goal.progress = 0
	# Clear the whole completion record, approval decision included — re-opening
	# means "this was never done", so a lingering approval stamp would be a lie.
	for f in (
		"submitted_at",
		"submitted_by",
		"numeric_value",
		"approved_by",
		"approved_at",
		"approval_notes",
	):
		if goal.meta.has_field(f):
			goal.set(f, None)
	goal.flags.ihc_governed_write = True
	goal.save(ignore_permissions=True)

	_pwa_refetch(
		list(_REQUESTER_CACHE_KEYS_BY_DOCTYPE["Goal"]), user=frappe.session.user
	)
	# The instance leaves the approver's pending queue when it is re-opened, so
	# refresh whoever was going to review it — but only if it was ever there.
	if was_in_approval_queue:
		for reviewer in _task_approver_audience(goal):
			_pwa_refetch(list(_INBOX_CACHE_KEYS), user=reviewer)
	return {"name": goal.name, "status": goal.status}


# --------------------------------------------------------------------------- #
# Head distribution (Assign-to-Head → split to reports → roll up)
# --------------------------------------------------------------------------- #
def _has_open_children(parent_name: str) -> bool:
	"""Does this Accountable instance have any not-yet-Completed distributed child?"""
	if not frappe.get_meta("Goal").has_field("accountable_parent"):
		return False
	return bool(
		frappe.db.exists(
			"Goal",
			{
				"accountable_parent": parent_name,
				"status": ("in", ["Pending", "In Progress"]),
			},
		)
	)


def _maybe_complete_accountable_parent(parent_name: str) -> None:
	"""Complete the head's parent instance once EVERY distributed child is done.

	The head's own instance is proof the whole obligation was met; it finishes
	when its children do, without the head touching it. If children remain, leave
	it open."""
	parent = frappe.db.get_value(
		"Goal", parent_name, ["name", "status"], as_dict=True
	)
	if not parent or parent.status == "Completed":
		return
	children = frappe.get_all(
		"Goal", filters={"accountable_parent": parent_name}, fields=["status"]
	)
	# Complete the parent once NO child is still open. Archived/Closed children
	# (e.g. the report left and HR shelved their instance) count as resolved, not
	# blockers — otherwise the parent would hang un-tickable forever. Require at
	# least one genuinely Completed child so an all-archived parent isn't
	# spuriously marked done.
	if not children:
		return
	if any(c.status in ("Pending", "In Progress") for c in children):
		return
	if not any(c.status == "Completed" for c in children):
		return
	doc = frappe.get_doc("Goal", parent_name)
	doc.status = "Completed"
	doc.progress = 100
	doc.flags.ihc_governed_write = True
	doc.save(ignore_permissions=True)
	# Nudge the head's screens.
	head_user = frappe.db.get_value("Employee", doc.employee, "user_id")
	if head_user:
		_pwa_refetch(list(_REQUESTER_CACHE_KEYS_BY_DOCTYPE["Goal"]), user=head_user)


@frappe.whitelist()
def distribute_task(goal_name: str, employees: str | list) -> dict:
	"""The head splits their Accountable instance into child instances for chosen
	reports. Each child carries `accountable_parent` (rollup lineage) and
	`delegated_from` (the head). The parent stays open and auto-completes when all
	children finish.

	Only the instance's own owner (the head) can distribute, only to their active
	DIRECT reports, and only an instance from an 'Assign to Head' task that hasn't
	already been distributed.
	"""
	if isinstance(employees, str):
		employees = frappe.parse_json(employees)
	employees = [e for e in (employees or []) if e]
	if not employees:
		frappe.throw(_("Pick at least one report to distribute to."))

	from indian_hrms_compliance.hr.doctype.hrms_task.hrms_task import _safe_pwa_notification

	me = get_current_employee()
	parent = frappe.get_doc("Goal", goal_name)
	if parent.goal_type != "Task Instance" or parent.employee != me:
		frappe.throw(_("You can only distribute your own task."), frappe.PermissionError)
	if not frappe.get_meta("Goal").has_field("accountable_parent"):
		frappe.throw(_("Distribution is not available on this site yet."))
	if parent.get("accountable_parent"):
		frappe.throw(_("This is already a distributed sub-task and can't be split again."))
	# Only an 'Assign to Head' instance may be distributed — otherwise an
	# individually-assigned (or leave-cover) instance could be offloaded and have
	# its accountability laundered away when a report ticks the child.
	template = parent.get("task_template")
	if not (template and frappe.db.get_value("HRMS Task", template, "assign_to_head")):
		frappe.throw(
			_("Only an 'Assign to Head' task can be distributed to your reports."),
			frappe.PermissionError,
		)
	# Don't distribute an instance that's already done or shelved.
	if parent.status not in ("Pending", "In Progress"):
		frappe.throw(_("Only an open task can be distributed."))
	if _has_open_children(parent.name):
		frappe.throw(_("This task has already been distributed."))

	# Reports must be the caller's own active direct reports IN THE SAME COMPANY
	# (tasks never cross company boundaries, mirroring the scheduler's fan-out).
	my_reports = set(
		frappe.get_all(
			"Employee",
			filters={"reports_to": me, "status": "Active", "company": parent.company},
			pluck="name",
		)
	)
	invalid = [e for e in employees if e not in my_reports]
	if invalid:
		frappe.throw(
			_("You can only distribute to your own active direct reports: {0} are not.").format(
				", ".join(invalid)
			)
		)

	# Children inherit the task's approval routing so an approval-gated sub-task
	# reaches the right approver (the head, under 'Reports To') instead of
	# stranding in HR's backstop queue.
	from indian_hrms_compliance.hr.doctype.hrms_task.hrms_task import resolve_instance_approver

	tmpl = frappe.get_doc("HRMS Task", template)
	has_role_field = frappe.get_meta("Goal").has_field("approver_role")

	created = []
	for emp in employees:
		e = frappe.db.get_value(
			"Employee",
			emp,
			["employee_name", "company", "user_id", "reports_to"],
			as_dict=True,
		)
		approver_user, approver_role = resolve_instance_approver(tmpl, e)
		values = {
			"doctype": "Goal",
			"goal_name": parent.goal_name,
			"employee": emp,
			"employee_name": e.employee_name,
			"company": e.company or parent.company,
			"goal_type": "Task Instance",
			"status": "Pending",
			"progress": 0,
			"kra": parent.get("kra"),
			"task_template": template,
			"period_label": parent.get("period_label"),
			"start_date": parent.get("start_date"),
			"end_date": parent.get("end_date"),
			"due_date": parent.get("due_date"),
			"accountable_parent": parent.name,
			"delegated_from": me,
			"approver_user": approver_user,
		}
		if approver_role and has_role_field:
			values["approver_role"] = approver_role
		child = frappe.get_doc(values)
		child.flags.ihc_governed_write = True
		child.insert(ignore_permissions=True)
		# A distributed child has NO performer until its assignee completes it.
		# `delegated_from` carries the head for lineage, but the head must NOT be
		# recorded as the doer — otherwise the segregation-of-duties gate would
		# refuse the head from approving their reports' sub-tasks.
		if child.get("performed_by"):
			frappe.db.set_value("Goal", child.name, "performed_by", None, update_modified=False)
		created.append(child.name)
		if e.user_id:
			_safe_pwa_notification(
				to_user=e.user_id,
				message=_("{0} distributed a task to you: {1}").format(
					frappe.db.get_value("Employee", me, "employee_name") or me, parent.goal_name
				),
				ref_type="Goal",
				ref_name=child.name,
			)
			_pwa_refetch(list(_REQUESTER_CACHE_KEYS_BY_DOCTYPE["Goal"]), user=e.user_id)

	# The parent is now awaiting its children — mark it In Progress so it isn't
	# mistaken for actionable-by-the-head work.
	if parent.status == "Pending":
		frappe.db.set_value("Goal", parent.name, {"status": "In Progress", "progress": 1}, update_modified=False)
	frappe.db.commit()
	return {"parent": parent.name, "children": created}


@frappe.whitelist()
def bounce_task(goal_name: str, comment: str) -> dict:
	"""Catchball-lite: a report returns a distributed sub-task to the head with a
	reason, instead of doing it. The child goes back to the head (who can
	re-distribute or do it), carrying the note."""
	from indian_hrms_compliance.hr.doctype.hrms_task.hrms_task import _safe_pwa_notification

	if not comment or not strip_html(comment).strip():
		frappe.throw(_("Say why you're bouncing it back."))
	me = get_current_employee()
	child = frappe.get_doc("Goal", goal_name)
	if child.goal_type != "Task Instance" or child.employee != me:
		frappe.throw(_("You can only bounce back your own task."), frappe.PermissionError)
	if not child.get("accountable_parent"):
		frappe.throw(_("This task wasn't distributed to you, so there's nothing to bounce."))

	parent = frappe.db.get_value(
		"Goal", child.accountable_parent, ["employee", "employee_name"], as_dict=True
	)
	if not parent:
		frappe.throw(_("The originating task no longer exists."))

	reason = strip_html(comment).strip()
	note = _("Bounced back by {0}: {1}").format(child.employee_name or me, reason)
	# Return the sub-task to the head, keeping the lineage + the reason.
	frappe.db.set_value(
		"Goal",
		child.name,
		{"employee": parent.employee, "employee_name": parent.employee_name, "status": "Pending", "progress": 0},
		update_modified=False,
	)
	if frappe.get_meta("Goal").has_field("task_notes"):
		frappe.db.set_value("Goal", child.name, "task_notes", note, update_modified=False)
	head_user = frappe.db.get_value("Employee", parent.employee, "user_id")
	if head_user:
		_safe_pwa_notification(
			to_user=head_user,
			message=_("A distributed task was bounced back to you: {0}").format(note),
			ref_type="Goal",
			ref_name=child.name,
		)
		_pwa_refetch(list(_REQUESTER_CACHE_KEYS_BY_DOCTYPE["Goal"]), user=head_user)
	frappe.db.commit()
	return {"name": child.name, "returned_to": parent.employee}


@frappe.whitelist()
def get_my_team():
	"""Who the current employee can assign ad-hoc tasks to: self (first), then
	their active direct reports. Self is always allowed so even non-managers
	can capture personal tasks on the My Tasks PWA screen."""
	employee = get_current_employee()
	me = frappe.db.get_value(
		"Employee", employee, ["name", "employee_name", "designation"], as_dict=True
	)
	team = frappe.get_all(
		"Employee",
		filters={"reports_to": employee, "status": "Active"},
		fields=["name", "employee_name", "designation"],
		order_by="employee_name asc",
	)
	if me:
		me_row = dict(me)
		me_row["employee_name"] = _("Myself ({0})").format(me.employee_name or me.name)
		me_row["is_self"] = 1
		return [me_row] + team
	return team


@frappe.whitelist()
def create_team_task(employee, title, due_date=None, description=None):
	"""A reporting manager (or HR) assigns a one-off task directly as a Goal
	(Task Instance) to a team member — one-off work lives as a Goal, not a
	recurring HRMS Task template."""
	manager = get_current_employee()
	if not title or not str(title).strip():
		frappe.throw(_("A task title is required."))

	target = frappe.db.get_value(
		"Employee", employee, ["name", "employee_name", "company", "reports_to", "user_id"], as_dict=True
	)
	if not target:
		frappe.throw(_("Employee not found."))

	is_hr = bool({"HR Manager", "HR User", "System Manager"} & set(frappe.get_roles()))
	is_self = target.name == manager
	if not is_self and target.reports_to != manager and not is_hr:
		frappe.throw(
			_("You can only assign ad-hoc tasks to yourself or your direct reports."),
			frappe.PermissionError,
		)

	today = frappe.utils.nowdate()
	due = due_date or today
	goal = frappe.get_doc(
		{
			"doctype": "Goal",
			"goal_type": "Task Instance",
			"goal_name": str(title).strip(),
			"employee": target.name,
			"employee_name": target.employee_name,
			"company": target.company,
			"status": "Pending",
			"start_date": today,
			"end_date": due,
			"due_date": due,
			"period_label": f"Ad-hoc {today}",
		}
	)
	if description and goal.meta.has_field("description"):
		goal.description = description
	goal.insert(ignore_permissions=True)

	# Don't ping the assignee if it's a self-assign — they just created it.
	if target.user_id and not is_self:
		from indian_hrms_compliance.hr.doctype.hrms_task.hrms_task import _safe_pwa_notification

		_safe_pwa_notification(
			to_user=target.user_id,
			message=_("New task assigned: {0} (due {1}).").format(goal.goal_name, due),
			ref_type="Goal",
			ref_name=goal.name,
		)
	# Live-refresh the assignee's My Tasks screen so the new card pops in
	# without a manual refresh. For self-assigns this is the current user.
	if target.user_id:
		_pwa_refetch(
			list(_REQUESTER_CACHE_KEYS_BY_DOCTYPE["Goal"]), user=target.user_id
		)
	return {"name": goal.name, "employee": target.name, "due_date": due, "is_self": int(is_self)}


# ---------------------------------------------------------------------------
# Phase 7C — Resignation & Exit (ESS)
# ---------------------------------------------------------------------------

# States from which an employee may still withdraw their own resignation.
_RESIGNATION_WITHDRAWABLE_STATES = (
	"Draft",
	"Pending Manager Acknowledgement",
)
# Resignation Requests in these states are considered "closed" — a new one is allowed.
_RESIGNATION_CLOSED_STATES = ("Withdrawn", "Rejected")

_RESIGNATION_STATUS_FIELDS = [
	"name",
	"request_type",
	"initiated_by",
	"submission_date",
	"reason_category",
	"reason_details",
	"notice_required_days",
	"notice_offered_days",
	"intended_last_working_date",
	"notice_disposition",
	"workflow_state",
	"linked_employee_separation",
	"linked_full_and_final",
]


@frappe.whitelist()
def get_my_resignation_status() -> dict:
	"""The current employee's most-recent Resignation Request, or {} if none.

	Surfaces only the fields the ESS exit tracker needs. The newest request
	(by submission_date, then creation) wins so a withdrawn-then-refiled
	employee sees the live one.
	"""
	employee = get_current_employee()
	rows = frappe.get_all(
		"Resignation Request",
		filters={"employee": employee},
		fields=_RESIGNATION_STATUS_FIELDS,
		order_by="submission_date desc, creation desc",
		limit=1,
	)
	if not rows:
		return {}
	row = rows[0]
	row["can_withdraw"] = row.get("workflow_state") in _RESIGNATION_WITHDRAWABLE_STATES
	return row


@frappe.whitelist()
def get_resignation_form_defaults() -> dict:
	"""Pre-fill values + Select options for the ESS resignation create form."""
	employee = get_current_employee()
	emp = frappe.db.get_value(
		"Employee",
		employee,
		["employee_name", "company", "notice_number_of_days", "date_of_joining"],
		as_dict=True,
	) or frappe._dict()

	reason_options = _select_options("Resignation Request", "reason_category")
	disposition_options = _select_options("Resignation Request", "notice_disposition")
	# Pay in Lieu of Notice is employer-only — never offer it to the employee.
	disposition_options = [d for d in disposition_options if d != "Pay in Lieu of Notice"]

	return {
		"employee": employee,
		"employee_name": emp.get("employee_name"),
		"company": emp.get("company"),
		"notice_required_days": emp.get("notice_number_of_days") or 0,
		"date_of_joining": emp.get("date_of_joining"),
		"reason_category_options": reason_options,
		"notice_disposition_options": disposition_options,
	}


def _select_options(doctype: str, fieldname: str) -> list[str]:
	"""Return the non-empty Select options for a doctype field."""
	meta = frappe.get_meta(doctype)
	field = meta.get_field(fieldname)
	if not field or not field.options:
		return []
	return [opt for opt in field.options.split("\n") if opt.strip()]


@frappe.whitelist()
def submit_resignation_request(
	reason_category: str,
	reason_details: str | None = None,
	notice_offered_days: int | None = None,
	notice_disposition: str | None = None,
	intended_last_working_date: str | None = None,
) -> dict:
	"""Create + submit an employee-initiated Resignation Request.

	Builds a request_type='Resignation' record for the active Employee with
	submission_date=today, then advances the workflow Draft → Pending Manager
	Acknowledgement via 'Submit Resignation'. Guards against a second active
	request and against the employer-only 'Pay in Lieu of Notice' disposition.
	"""
	from frappe.model.workflow import apply_workflow

	employee = get_current_employee()

	# Guard: one active resignation at a time.
	existing = frappe.get_all(
		"Resignation Request",
		filters={"employee": employee},
		fields=["name", "workflow_state"],
		order_by="submission_date desc, creation desc",
		limit=1,
	)
	if existing and existing[0].get("workflow_state") not in _RESIGNATION_CLOSED_STATES:
		frappe.throw(
			_(
				"You already have an active Resignation Request ({0}) in state '{1}'. "
				"Withdraw it before filing a new one."
			).format(existing[0].name, existing[0].get("workflow_state"))
		)

	if notice_disposition == "Pay in Lieu of Notice":
		# Surface the controller rule cleanly before it throws on insert.
		frappe.throw(
			_(
				"'Pay in Lieu of Notice' is for employer-initiated cases. "
				"Choose 'Will Serve in Full' or 'Short Notice (recovery)'."
			)
		)

	doc = frappe.get_doc(
		{
			"doctype": "Resignation Request",
			"request_type": "Resignation",
			"employee": employee,
			"submission_date": getdate(),
			"reason_category": reason_category,
			"reason_details": reason_details,
			"notice_offered_days": notice_offered_days,
			"notice_disposition": notice_disposition or "Will Serve in Full",
			"intended_last_working_date": intended_last_working_date,
		}
	)
	doc.insert(ignore_permissions=True)

	# Advance Draft → Pending Manager Acknowledgement.
	apply_workflow(doc, "Submit Resignation")

	return {"name": doc.name, "workflow_state": doc.workflow_state}


@frappe.whitelist()
def withdraw_resignation_request(name: str) -> dict:
	"""Ownership-guarded withdrawal of the employee's own Resignation Request."""
	from frappe.model.workflow import apply_workflow

	employee = get_current_employee()
	doc = frappe.get_doc("Resignation Request", name)
	if doc.employee != employee:
		frappe.throw(
			_("You are not permitted to withdraw this Resignation Request."),
			frappe.PermissionError,
		)
	if doc.workflow_state not in _RESIGNATION_WITHDRAWABLE_STATES:
		frappe.throw(
			_("This Resignation Request can no longer be withdrawn (state: {0}).").format(
				doc.workflow_state
			)
		)
	apply_workflow(doc, "Withdraw")
	return {"name": doc.name, "workflow_state": doc.workflow_state}


@frappe.whitelist()
def get_my_exit_clearance() -> dict:
	"""Read-only no-dues clearance view for the active Employee.

	Resolves the Employee Separation linked to the employee's latest
	Resignation Request (falling back to the most-recent Separation for the
	employee), and returns its no_dues_items + overall boarding_status.
	Returns {} when there's no separation yet.
	"""
	employee = get_current_employee()

	sep_name = None
	status = get_my_resignation_status()
	if status.get("linked_employee_separation"):
		sep_name = status["linked_employee_separation"]
	if not sep_name:
		rows = frappe.get_all(
			"Employee Separation",
			filters={"employee": employee},
			fields=["name"],
			order_by="creation desc",
			limit=1,
		)
		if rows:
			sep_name = rows[0].name
	if not sep_name:
		return {}

	sep = frappe.get_doc("Employee Separation", sep_name)
	items = []
	for row in sep.get("no_dues_items") or []:
		owner_name = None
		if row.clearance_owner:
			owner_name = frappe.db.get_value("User", row.clearance_owner, "full_name")
		items.append(
			{
				"clearance_area": row.clearance_area,
				"clearance_owner": owner_name or row.clearance_owner,
				"description": row.description,
				"status": row.status,
				"blocking": int(row.blocking or 0),
			}
		)

	return {
		"name": sep.name,
		"boarding_status": sep.get("boarding_status"),
		"no_dues_items": items,
	}


@frappe.whitelist()
def get_my_exit_documents() -> dict:
	"""Downloadable exit documents for the active Employee.

	- Exit letters: finalised Appointment Letter records (Relieving / Experience
	  / Service Certificate) for this employee, exposed via the print view URL.
	- Form 16: only those with issue_status='Issued' that carry a signed PDF.
	"""
	employee = get_current_employee()

	exit_letter_types = ("Relieving Letter", "Experience Letter", "Service Certificate")
	letters = []
	for row in frappe.get_all(
		"Appointment Letter",
		filters={
			"employee": employee,
			"letter_type": ["in", exit_letter_types],
		},
		fields=["name", "letter_type", "company", "appointment_date"],
		order_by="appointment_date desc, creation desc",
	):
		letters.append(
			{
				"name": row.name,
				"letter_type": row.letter_type,
				"company": row.company,
				"date": row.appointment_date,
				"print_url": (
					f"/printview?doctype=Appointment%20Letter&name={frappe.utils.quote(row.name)}"
					"&format=Standard%20Appointment%20Letter&trigger_print=1"
				),
			}
		)

	form16 = []
	for row in frappe.get_all(
		"Form 16",
		filters={"employee": employee, "issue_status": "Issued"},
		fields=["name", "fiscal_year", "company", "issue_status", "issued_on", "signed_pdf"],
		order_by="fiscal_year desc",
	):
		if not row.signed_pdf:
			continue
		form16.append(
			{
				"name": row.name,
				"fiscal_year": row.fiscal_year,
				"company": row.company,
				"issue_status": row.issue_status,
				"issued_on": row.issued_on,
				"signed_pdf": row.signed_pdf,
			}
		)

	return {"letters": letters, "form16": form16}


# ---------------------------------------------------------------------------
# Phase 7D — Grievance + POSH (ESS PWA)
# ---------------------------------------------------------------------------

_GRIEVANCE_LIST_FIELDS = [
	"name",
	"subject",
	"grievance_type",
	"severity",
	"status",
	"workflow_state",
	"sla_due_date",
	"creation",
	"description",
	"resolution_detail",
	"date",
]

_GRIEVANCE_SEVERITY_OPTIONS = ["Low", "Medium", "High", "Critical"]


@frappe.whitelist()
def get_my_grievances() -> list[dict]:
	"""The current employee's grievances (raised_by = active Employee).

	Newest first. Returns the subset of fields the ESS grievance tracker
	needs — never anyone else's grievances."""
	employee = get_current_employee()
	return frappe.get_all(
		"Employee Grievance",
		filters={"raised_by": employee},
		fields=_GRIEVANCE_LIST_FIELDS,
		order_by="creation desc",
	)


@frappe.whitelist()
def get_grievance_form_options() -> dict:
	"""Select options for the ESS grievance create form: grievance types
	(with their default severity so the form can pre-fill) + severities."""
	# default_severity is a Custom Field — guard the read so a site that hasn't
	# synced it yet (mid-migrate / drift) still returns the type list instead of
	# throwing "Unknown column" and leaving the whole form's dropdown empty.
	fields = ["name"]
	if frappe.get_meta("Grievance Type").has_field("default_severity"):
		fields.append("default_severity")
	grievance_types = frappe.get_all(
		"Grievance Type",
		fields=fields,
		order_by="name asc",
	)
	return {
		"grievance_types": grievance_types,
		"severity_options": _GRIEVANCE_SEVERITY_OPTIONS,
	}


@frappe.whitelist()
def file_grievance(
	subject: str,
	grievance_type: str,
	description: str,
	severity: str | None = None,
) -> dict:
	"""Create an employee-raised Employee Grievance in the Open state.

	raised_by = active Employee, company from that Employee. The grievance
	is filed about the organisation (grievance_against_party='Company',
	grievance_against=company) by default so the employee never has to
	name an individual to lodge a concern. Severity falls back to the
	Grievance Type default, then 'Medium'."""
	employee = get_current_employee()
	emp = frappe.db.get_value(
		"Employee", employee, ["company", "employee_name"], as_dict=True
	) or frappe._dict()

	if not severity and grievance_type and frappe.get_meta("Grievance Type").has_field(
		"default_severity"
	):
		severity = (
			frappe.db.get_value("Grievance Type", grievance_type, "default_severity")
			or "Medium"
		)

	doc = frappe.get_doc(
		{
			"doctype": "Employee Grievance",
			"subject": subject,
			"raised_by": employee,
			"date": getdate(),
			"status": "Open",
			"grievance_type": grievance_type,
			"severity": severity or "Medium",
			"description": description,
			"grievance_against_party": "Company",
			"grievance_against": emp.get("company"),
		}
	)
	doc.insert(ignore_permissions=True)

	return {
		"name": doc.name,
		"workflow_state": doc.workflow_state or doc.status,
		"status": doc.status,
	}


# ---- POSH (confidential) ----

_POSH_LIST_FIELDS = [
	"name",
	"filing_date",
	"workflow_state",
	"sla_due_date",
	"anonymous",
	"incident_date",
]

_POSH_STEPS = [
	"Filed",
	"Acknowledged",
	"Inquiry",
	"Findings Recorded",
	"Action Recommended",
	"Closed",
]


@frappe.whitelist()
def get_my_posh_complaints() -> list[dict]:
	"""The current employee's own POSH complaints (complainant = active
	Employee).

	Confidentiality: the hard guard is the explicit ``complainant`` filter —
	the user can only ever receive their own complaints. We pass
	``ignore_permissions=True`` deliberately: the standard user-permission
	link-field filter would otherwise drop a complaint because its ``accused``
	Employee is one the complainant has no User Permission for. Our own
	per-record check (get_posh_complaint_detail → has_permission) and the
	permission_query_conditions hook remain the gate for detail access.
	The list is deliberately lean — no accused identity, no incident
	description here."""
	employee = get_current_employee()
	return frappe.get_list(
		"POSH Complaint",
		filters={"complainant": employee},
		fields=_POSH_LIST_FIELDS,
		order_by="filing_date desc, creation desc",
		ignore_permissions=True,
	)


@frappe.whitelist()
def get_posh_complaint_detail(name: str) -> dict:
	"""Detail for a single POSH complaint, gated by the confidentiality hook.

	Verifies the current user may read this specific record (complainant,
	accused, or active IC member per overrides/posh_access.py) before
	returning any incident detail. Throws PermissionError otherwise so the
	PWA can never leak a complaint to the wrong person.

	We call posh_complaint_has_permission directly rather than
	frappe.has_permission: the latter additionally ANDs standard
	user-permission link-field checks, which spuriously deny the legitimate
	complainant when the ``accused`` Employee is one they hold no User
	Permission for. The hook IS the authoritative confidentiality rule."""
	from indian_hrms_compliance.overrides.posh_access import posh_complaint_has_permission

	doc = frappe.get_doc("POSH Complaint", name)
	if not posh_complaint_has_permission(doc, frappe.session.user):
		frappe.throw(
			_("You are not permitted to view this complaint."),
			frappe.PermissionError,
		)
	return {
		"name": doc.name,
		"workflow_state": doc.workflow_state,
		"filing_date": doc.filing_date,
		"sla_due_date": doc.sla_due_date,
		"anonymous": doc.anonymous,
		"incident_date": doc.incident_date,
		"incident_location": doc.incident_location,
		"incident_description": doc.incident_description,
		"steps": _POSH_STEPS,
	}


@frappe.whitelist()
def file_posh_complaint(
	accused: str,
	incident_date: str,
	incident_description: str,
	incident_location: str | None = None,
	anonymous: int | str = 0,
) -> dict:
	"""File a confidential POSH complaint for the active Employee.

	complainant = active Employee, company from that Employee, filing_date
	= today. The controller auto-links the company's Active Internal
	Committee on insert. If no Active IC exists for the company we surface
	a clear, non-crashing message asking the employee to contact HR."""
	employee = get_current_employee()
	emp = frappe.db.get_value(
		"Employee", employee, ["company"], as_dict=True
	) or frappe._dict()
	company = emp.get("company")

	# Guard: an Active IC must exist for the complainant's Company.
	has_ic = frappe.db.exists(
		"POSH Internal Committee", {"company": company, "status": "Active"}
	)
	if not has_ic:
		frappe.throw(
			_(
				"No active Internal Committee (IC) is currently constituted for {0}. "
				"Please contact HR — a complaint cannot be filed until an IC exists."
			).format(company or _("your company"))
		)

	doc = frappe.get_doc(
		{
			"doctype": "POSH Complaint",
			"company": company,
			"complainant": employee,
			"filing_date": getdate(),
			"accused": accused,
			"incident_date": incident_date,
			"incident_description": incident_description,
			"incident_location": incident_location,
			"anonymous": 1 if str(anonymous) in ("1", "true", "True") else 0,
		}
	)
	doc.insert(ignore_permissions=True)

	return {"name": doc.name, "workflow_state": doc.workflow_state}


@frappe.whitelist()
def get_posh_help_info() -> dict:
	"""Statutory help + IC availability for the active Employee's Company.

	Confidentiality: exposes only whether an Active IC exists and its
	member count — never member identities. Used to gate the 'File a
	Complaint' action and show statutory guidance."""
	employee = get_current_employee()
	company = frappe.db.get_value("Employee", employee, "company")

	ic = frappe.db.get_value(
		"POSH Internal Committee",
		{"company": company, "status": "Active"},
		"name",
		order_by="constitution_date desc",
	)
	member_count = 0
	if ic:
		member_count = frappe.db.count(
			"POSH IC Member", {"parent": ic, "is_active": 1}
		)

	return {
		"company": company,
		"has_active_ic": bool(ic),
		"ic_member_count": member_count,
		"sla_days": 90,
		"help_text": _(
			"Complaints under the Sexual Harassment of Women at Workplace "
			"(Prevention, Prohibition and Redressal) Act, 2013 are handled in "
			"strict confidence by the Internal Committee (IC). The IC must "
			"complete its inquiry within 90 days. Only you, the respondent, and "
			"active IC members can access your complaint — not HR or your manager."
		),
	}


# ---- DPDP: Consent management + Right-to-access / erasure (Phase 7E) ----

# Static map of the personal-data categories the organisation holds about an
# employee, with the DPDP lawful basis + retention guidance. Informational only
# — get_my_data_summary never returns actual field VALUES, just the categories.
_DPDP_DATA_CATEGORIES = [
	{
		"category": "Identity",
		"examples": "Name, date of birth, gender",
		"lawful_basis": "Contract Performance",
		"retention": "Duration of employment + statutory period",
	},
	{
		"category": "Contact",
		"examples": "Personal email, phone, address",
		"lawful_basis": "Contract Performance",
		"retention": "Duration of employment + statutory period",
	},
	{
		"category": "Statutory IDs",
		"examples": "PAN, UAN, ESIC, Aadhaar (last 4 digits)",
		"lawful_basis": "Statutory Obligation",
		"retention": "Up to 8 years (Income Tax Act) / 7 years (PF & ESI)",
	},
	{
		"category": "Financial",
		"examples": "Bank account details, salary structure",
		"lawful_basis": "Contract Performance",
		"retention": "Up to 8 years (Income Tax Act)",
	},
	{
		"category": "Employment",
		"examples": "Designation, department, joining & relieving dates",
		"lawful_basis": "Contract Performance",
		"retention": "Duration of employment + statutory period",
	},
	{
		"category": "Performance",
		"examples": "Appraisals, goals, review notes",
		"lawful_basis": "Legitimate Interest",
		"retention": "Duration of employment",
	},
	{
		"category": "Attendance",
		"examples": "Check-in/out, attendance records",
		"lawful_basis": "Contract Performance",
		"retention": "Duration of employment + statutory period",
	},
	{
		"category": "Leave",
		"examples": "Leave applications, balances",
		"lawful_basis": "Contract Performance",
		"retention": "Duration of employment + statutory period",
	},
]


def _dpdp_consent_status(consent_status: str | None) -> str:
	"""Normalise a Data Consent.consent_status into the 3 states the ESS
	consent dashboard shows: 'Active', 'Withdrawn' or 'Not Given'."""
	if consent_status == "Active":
		return "Active"
	if consent_status == "Withdrawn":
		return "Withdrawn"
	return "Not Given"


def _get_dpo_email() -> str | None:
	"""Data Protection Officer contact email from the (Single) DPDP Compliance
	Profile, used as the rights-request contact. None if unset."""
	try:
		return frappe.db.get_single_value("DPDP Compliance Profile", "dpo_email") or None
	except Exception:
		return None


@frappe.whitelist()
def get_my_consent_overview() -> list[dict]:
	"""DPDP consent dashboard for the current employee.

	Lists every Active Data Consent Purpose and overlays the employee's
	current consent status for each (Active / Withdrawn / Not Given). Reads
	the latest Data Consent row per purpose so a re-grant after a withdrawal
	shows as Active again. Never exposes other employees' consents."""
	employee = get_current_employee()

	purposes = frappe.get_all(
		"Data Consent Purpose",
		filters={"is_active": 1},
		fields=[
			"name",
			"purpose_code",
			"purpose_name",
			"description",
			"data_categories",
			"lawful_basis",
			"requires_explicit_consent",
			"withdrawal_consequences",
			"retention_period_years",
		],
		order_by="purpose_name asc",
	)

	overview = []
	for p in purposes:
		consent = frappe.db.get_value(
			"Data Consent",
			{"employee": employee, "purpose": p.name},
			["name", "consent_status", "granted_on", "expires_on"],
			as_dict=True,
			order_by="granted_on desc, creation desc",
		)
		overview.append(
			{
				"purpose_code": p.purpose_code,
				"purpose_name": p.purpose_name,
				"description": p.description,
				"data_categories": p.data_categories,
				"lawful_basis": p.lawful_basis,
				"requires_explicit_consent": p.requires_explicit_consent,
				"withdrawal_consequences": p.withdrawal_consequences,
				"retention_period_years": p.retention_period_years,
				"consent_status": _dpdp_consent_status(
					consent.consent_status if consent else None
				),
				"consent_name": consent.name if consent else None,
				"granted_on": consent.granted_on if consent else None,
				"expires_on": consent.expires_on if consent else None,
			}
		)
	return overview


@frappe.whitelist()
def get_consent_notice(purpose_code: str) -> dict:
	"""The DPDP Sec 5 notice for a purpose, rendered for the current employee.

	Renders the purpose's Jinja notice_template with employee context. Falls
	back to the description when no template is set. Returns the purpose meta
	the ConsentNoticeView needs to show lawful basis, retention, withdrawal
	consequences and the current grant/withdraw state."""
	employee = get_current_employee()
	purpose = frappe.db.get_value(
		"Data Consent Purpose",
		{"purpose_code": purpose_code, "is_active": 1},
		[
			"name",
			"purpose_code",
			"purpose_name",
			"description",
			"data_categories",
			"lawful_basis",
			"requires_explicit_consent",
			"withdrawal_consequences",
			"retention_period_years",
			"notice_template",
		],
		as_dict=True,
	)
	if not purpose:
		frappe.throw(_("Data processing purpose {0} not found.").format(purpose_code))

	emp = frappe.db.get_value(
		"Employee", employee, ["employee_name", "company"], as_dict=True
	) or frappe._dict()

	notice_html = ""
	if purpose.notice_template:
		try:
			notice_html = frappe.render_template(
				purpose.notice_template,
				{
					"employee_name": emp.get("employee_name") or "",
					"company": emp.get("company") or "",
					"purpose_name": purpose.purpose_name,
				},
			)
		except Exception:
			notice_html = purpose.notice_template
			frappe.log_error(
				title=f"DPDP notice render failed: {purpose_code}",
				message=frappe.get_traceback(),
			)

	consent = frappe.db.get_value(
		"Data Consent",
		{"employee": employee, "purpose": purpose.name},
		["name", "consent_status", "granted_on", "expires_on"],
		as_dict=True,
		order_by="granted_on desc, creation desc",
	)

	return {
		"purpose_code": purpose.purpose_code,
		"purpose_name": purpose.purpose_name,
		"description": purpose.description,
		"data_categories": purpose.data_categories,
		"lawful_basis": purpose.lawful_basis,
		"requires_explicit_consent": purpose.requires_explicit_consent,
		"withdrawal_consequences": purpose.withdrawal_consequences,
		"retention_period_years": purpose.retention_period_years,
		"notice_html": notice_html,
		"consent_status": _dpdp_consent_status(
			consent.consent_status if consent else None
		),
		"consent_name": consent.name if consent else None,
		"granted_on": consent.granted_on if consent else None,
		"expires_on": consent.expires_on if consent else None,
	}


@frappe.whitelist()
def grant_consent(purpose_code: str) -> dict:
	"""Capture (or reactivate) the current employee's consent for a purpose.

	Creates a Data Consent row via the Web Form method, snapshotting the
	rendered notice. If an Active consent already exists it is a no-op and
	the existing row is returned. A previously-withdrawn row is left intact
	(audit trail) and a fresh Active row is captured."""
	employee = get_current_employee()
	purpose = frappe.db.get_value(
		"Data Consent Purpose",
		{"purpose_code": purpose_code, "is_active": 1},
		["name", "purpose_name"],
		as_dict=True,
	)
	if not purpose:
		frappe.throw(_("Data processing purpose {0} not found.").format(purpose_code))

	existing = frappe.db.get_value(
		"Data Consent",
		{"employee": employee, "purpose": purpose.name, "consent_status": "Active"},
		"name",
	)
	if existing:
		return {"name": existing, "consent_status": "Active", "created": False}

	notice = get_consent_notice(purpose_code)

	doc = frappe.get_doc(
		{
			"doctype": "Data Consent",
			"employee": employee,
			"purpose": purpose.name,
			"granted_on": getdate(),
			"consent_method": "Web Form",
			"consent_status": "Active",
			"notice_shown_html": notice.get("notice_html") or "",
		}
	)
	doc.insert(ignore_permissions=True)

	return {
		"name": doc.name,
		"consent_status": doc.consent_status,
		"granted_on": doc.granted_on,
		"expires_on": doc.expires_on,
		"created": True,
	}


@frappe.whitelist()
def withdraw_consent(purpose_code: str, reason: str | None = None) -> dict:
	"""Withdraw the current employee's Active consent for a purpose.

	Sets consent_status='Withdrawn', withdrawn_on=today and records the
	reason. The row is NOT deleted (DPDP Sec 13 audit trail). Statutory
	Obligation purposes cannot be withdrawn — the organisation must process
	that data under a legal duty — so we reject with a clear explanation."""
	employee = get_current_employee()
	purpose = frappe.db.get_value(
		"Data Consent Purpose",
		{"purpose_code": purpose_code},
		["name", "lawful_basis", "purpose_name"],
		as_dict=True,
	)
	if not purpose:
		frappe.throw(_("Data processing purpose {0} not found.").format(purpose_code))

	if purpose.lawful_basis == "Statutory Obligation":
		frappe.throw(
			_(
				"Consent for '{0}' cannot be withdrawn. This data is processed "
				"under a statutory obligation (e.g. payroll, tax and provident "
				"fund law), not under your consent, so the organisation is "
				"legally required to continue processing it."
			).format(purpose.purpose_name)
		)

	consent = frappe.db.get_value(
		"Data Consent",
		{"employee": employee, "purpose": purpose.name, "consent_status": "Active"},
		"name",
	)
	if not consent:
		frappe.throw(
			_("You have no active consent to withdraw for '{0}'.").format(
				purpose.purpose_name
			)
		)

	doc = frappe.get_doc("Data Consent", consent)
	doc.consent_status = "Withdrawn"
	doc.withdrawn_on = getdate()
	if reason:
		doc.withdrawal_reason = reason
	doc.save(ignore_permissions=True)

	return {
		"name": doc.name,
		"consent_status": doc.consent_status,
		"withdrawn_on": doc.withdrawn_on,
	}


@frappe.whitelist()
def get_my_data_summary() -> dict:
	"""DPDP Sec 11 right-to-access summary for the current employee.

	Returns the CATEGORIES of personal data the organisation holds, each with
	its lawful basis + retention guidance — deliberately NOT the actual values
	— plus the Data Protection Officer contact for exercising data-principal
	rights. Informational; pairs with the consent dashboard + erasure flow."""
	# Resolve employee (ensures an Active employment context exists).
	get_current_employee()
	return {
		"categories": _DPDP_DATA_CATEGORIES,
		"dpo_email": _get_dpo_email(),
	}


_DPDP_ERASURE_OPEN_STATES = ("Filed", "Under Legal Review", "Decision Made")
_DPDP_ERASURE_LIST_FIELDS = [
	"name",
	"request_date",
	"scope",
	"workflow_state",
	"decision",
]


@frappe.whitelist()
def request_data_erasure(
	scope: str,
	specific_categories: str | None = None,
	reason: str | None = None,
) -> dict:
	"""File a DPDP Sec 12 right-to-erasure request for the current employee.

	requested_by = current user, request_date = today, workflow_state =
	'Filed' (mandatory legal review follows). Rejects if the employee already
	has an open (non-terminal) erasure request so duplicates don't pile up.
	Statutory data may ultimately be retained — that is decided in review."""
	employee = get_current_employee()

	open_existing = frappe.db.exists(
		"Data Erasure Request",
		{"employee": employee, "workflow_state": ["in", _DPDP_ERASURE_OPEN_STATES]},
	)
	if open_existing:
		frappe.throw(
			_(
				"You already have an open data erasure request ({0}). Please wait "
				"for it to be reviewed before filing another."
			).format(open_existing)
		)

	if scope not in ("Full Profile", "Specific Data Categories"):
		frappe.throw(_("Invalid scope."))

	doc = frappe.get_doc(
		{
			"doctype": "Data Erasure Request",
			"employee": employee,
			"request_date": getdate(),
			"requested_by": frappe.session.user,
			"scope": scope,
			"specific_categories": specific_categories
			if scope == "Specific Data Categories"
			else None,
			"workflow_state": "Filed",
			"notes": reason,
		}
	)
	doc.insert(ignore_permissions=True)

	return {"name": doc.name, "workflow_state": doc.workflow_state}


@frappe.whitelist()
def get_my_erasure_requests() -> list[dict]:
	"""The current employee's own Data Erasure Requests, newest first."""
	employee = get_current_employee()
	return frappe.get_all(
		"Data Erasure Request",
		filters={"employee": employee},
		fields=_DPDP_ERASURE_LIST_FIELDS,
		order_by="request_date desc, creation desc",
	)


# ---------------------------------------------------------------------------
# Phase 7F — Manager Mobile Approvals inbox
# ---------------------------------------------------------------------------
#
# A unified inbox of everything awaiting the current user's action AS AN
# APPROVER (not as an employee). Aggregates six request types; each item is
# tagged with the doctype, an action_type, and a category so the PWA can group
# and act on it. SECURITY: approve_request / reject_request re-derive the
# authorized approver server-side for the specific record and refuse anyone
# else — the inbox listing is only a convenience, never the authorization.

# Category labels surfaced to the PWA segment filter / badges.
_APPROVAL_CATEGORIES = (
	"Leave",
	"Expense",
	"Advance",
	"Shift",
	"Attendance",
	"Task",
	"Resignation",
	"Profile Update",
	"Onboarding",
	"Grievance",
)
_HR_APPROVER_ROLES = frozenset(("HR Manager", "HR User", "System Manager"))


def _is_hr_user(user: str) -> bool:
	"""True if ``user`` holds any HR-level role. The Profile Update, Onboarding
	Application, and Grievance categories are gated on HR membership rather
	than a per-record approver field."""
	roles = set(frappe.get_roles(user))
	return bool(_HR_APPROVER_ROLES & roles)


def _hr_company_scope(user: str) -> list[str] | None:
	"""Companies an HR user should see records for.

	Returns:
	  - list of Company names → restrict to these
	  - None → no restriction (HR user has no User Permission rows for Company)

	System Manager always returns None (sees everything). Otherwise we read
	the active User Permissions: an HR Manager with User Permission rows for
	"Acme India" + "Acme Singapore" only sees inbox items in those companies.
	If they have no User Permission rows at all, we don't filter (matches
	Frappe's default behaviour when no perms are configured).
	"""
	if "System Manager" in frappe.get_roles(user):
		return None
	companies = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Company"},
		pluck="for_value",
	)
	companies = [c for c in companies if c]
	return companies or None


def _approver_employees_for_user(user: str) -> list[str]:
	"""Active Employee names linked to ``user`` (a user may map to several)."""
	return frappe.get_all(
		"Employee",
		filters={"user_id": user, "status": "Active"},
		pluck="name",
	)


def _resignation_reports_to_user(user: str) -> set[str]:
	"""Employee names whose ``reports_to`` resolves to an Employee owned by ``user``.

	Used to decide which Resignation Requests this user may acknowledge as the
	reporting manager.
	"""
	manager_emps = _approver_employees_for_user(user)
	if not manager_emps:
		return set()
	return set(
		frappe.get_all(
			"Employee",
			filters={"reports_to": ("in", manager_emps)},
			pluck="name",
		)
	)


def _pending_leave_approvals(user: str) -> list[dict]:
	rows = frappe.get_all(
		"Leave Application",
		filters={"status": "Open", "leave_approver": user, "docstatus": 0},
		fields=[
			"name",
			"employee",
			"employee_name",
			"leave_type",
			"from_date",
			"to_date",
			"total_leave_days",
			"posting_date",
		],
		order_by="posting_date desc",
	)
	out = []
	for r in rows:
		dates = (
			str(getdate(r.from_date))
			if r.from_date == r.to_date
			else f"{getdate(r.from_date)} → {getdate(r.to_date)}"
		)
		out.append(
			{
				"doctype": "Leave Application",
				"name": r.name,
				"category": "Leave",
				"title": _("Leave: {0}").format(r.leave_type),
				"subtitle": _("{0} ({1} day(s))").format(dates, flt(r.total_leave_days)),
				"employee": r.employee,
				"employee_name": r.employee_name,
				"date": str(r.posting_date) if r.posting_date else None,
				"action_type": "status",
			}
		)
	return out


def _pending_expense_approvals(user: str) -> list[dict]:
	rows = frappe.get_all(
		"Expense Claim",
		filters={
			"approval_status": ("in", ["Draft", "Submitted"]),
			"expense_approver": user,
			"docstatus": 0,
		},
		fields=[
			"name",
			"employee",
			"employee_name",
			"total_claimed_amount",
			"company",
			"posting_date",
		],
		order_by="posting_date desc",
	)
	out = []
	for r in rows:
		out.append(
			{
				"doctype": "Expense Claim",
				"name": r.name,
				"category": "Expense",
				"title": _("Expense Claim"),
				"subtitle": _("Amount: {0}").format(flt(r.total_claimed_amount)),
				"employee": r.employee,
				"employee_name": r.employee_name,
				"date": str(r.posting_date) if r.posting_date else None,
				"action_type": "status",
			}
		)
	return out


def _pending_advance_approvals(user: str) -> list[dict]:
	"""Employee Advances awaiting approval (Draft, docstatus 0) whose employee
	reports to this manager. Employee Advance has no approver field — the
	manager authority is the reporting line."""
	reports = _resignation_reports_to_user(user)
	if not reports:
		return []
	rows = frappe.get_all(
		"Employee Advance",
		filters={"status": "Draft", "docstatus": 0, "employee": ("in", list(reports))},
		fields=[
			"name",
			"employee",
			"employee_name",
			"purpose",
			"advance_amount",
			"posting_date",
		],
		order_by="posting_date desc",
	)
	out = []
	for r in rows:
		out.append(
			{
				"doctype": "Employee Advance",
				"name": r.name,
				"category": "Advance",
				"title": _("Advance: {0}").format(flt(r.advance_amount)),
				"subtitle": strip_html(r.purpose or "").strip()[:120],
				"employee": r.employee,
				"employee_name": r.employee_name,
				"date": str(r.posting_date) if r.posting_date else None,
				"action_type": "status",
			}
		)
	return out


def _pending_shift_approvals(user: str) -> list[dict]:
	rows = frappe.get_all(
		"Shift Request",
		filters={"status": "Draft", "approver": user, "docstatus": 0},
		fields=[
			"name",
			"employee",
			"employee_name",
			"shift_type",
			"from_date",
			"to_date",
			"creation",
		],
		order_by="creation desc",
	)
	out = []
	for r in rows:
		out.append(
			{
				"doctype": "Shift Request",
				"name": r.name,
				"category": "Shift",
				"title": _("Shift: {0}").format(r.shift_type),
				"subtitle": f"{getdate(r.from_date)} → {getdate(r.to_date)}"
				if r.to_date
				else str(getdate(r.from_date)),
				"employee": r.employee,
				"employee_name": r.employee_name,
				"date": str(getdate(r.creation)) if r.creation else None,
				"action_type": "status",
			}
		)
	return out


def _pending_attendance_approvals(user: str) -> list[dict]:
	"""Attendance Requests (no approver field) awaiting submission, scoped to
	this manager's direct reports."""
	filters: dict = {"docstatus": 0}
	# Only genuinely-pending requests belong in the approver queue — a Rejected
	# (terminal) or Needs Clarification (back with the employee) draft is not
	# awaiting this manager.
	if frappe.get_meta("Attendance Request").has_field("status"):
		filters["status"] = "Open"

	# HR sees every pending request in their companies (they own this process);
	# a plain reporting manager sees only their direct reports.
	if _is_hr_user(user):
		scope = _hr_company_scope(user)
		if scope is not None:
			filters["company"] = ("in", scope)
	else:
		reports = _resignation_reports_to_user(user)
		if not reports:
			return []
		filters["employee"] = ("in", list(reports))
	rows = frappe.get_all(
		"Attendance Request",
		filters=filters,
		fields=[
			"name",
			"employee",
			"employee_name",
			"reason",
			"from_date",
			"to_date",
			"creation",
		],
		order_by="creation desc",
	)
	out = []
	for r in rows:
		out.append(
			{
				"doctype": "Attendance Request",
				"name": r.name,
				"category": "Attendance",
				"title": _("Attendance Request"),
				"subtitle": f"{getdate(r.from_date)} → {getdate(r.to_date)}"
				if r.to_date
				else str(getdate(r.from_date)),
				"employee": r.employee,
				"employee_name": r.employee_name,
				"date": str(getdate(r.creation)) if r.creation else None,
				# full timestamp so same-day requests still sort newest-first
				"_ts": str(r.creation) if r.creation else None,
				"action_type": "status",
			}
		)
	return out


def _pending_task_approvals(user: str) -> list[dict]:
	"""Task Instances submitted for approval and awaiting THIS user's decision.

	A submitted-but-undecided instance sits at status 'In Progress' with a
	non-null submitted_at. Three routes can bring it here:

	  1. ``approver_user`` is this user (the common case).
	  2. ``approver_role`` is a role this user holds — role-routed approval, so
		 any holder can act and nothing dies with one person's account.
	  3. It is UNROUTED (no approver_user and no approver_role) and this user is
		 HR. Without this, an instance whose approver could not be resolved
		 would be invisible in every inbox and stay stuck forever.
	"""
	base = {
		"goal_type": "Task Instance",
		"status": "In Progress",
		"submitted_at": ("is", "set"),
	}
	fields = [
		"name",
		"employee",
		"employee_name",
		"goal_name",
		"period_label",
		"due_date",
		"submitted_at",
		"approver_user",
		# Needed to work out who DID the task, so we never list an instance in the
		# inbox of someone the approval gate would then refuse.
		"submitted_by",
		"performed_by",
	]
	has_role_field = frappe.get_meta("Goal").has_field("approver_role")
	if has_role_field:
		fields.append("approver_role")

	collected: dict[str, dict] = {}

	def _collect(filters: dict) -> None:
		for row in frappe.get_all("Goal", filters=filters, fields=fields, order_by="submitted_at desc"):
			collected.setdefault(row.name, row)

	# 1. Directly assigned.
	_collect({**base, "approver_user": user})

	# 2. Role-routed — any holder of the role may approve.
	if has_role_field:
		roles = [r for r in frappe.get_roles(user) if r not in ("All", "Guest")]
		if roles:
			_collect({**base, "approver_role": ("in", roles)})

	# 3. Unrouted OR stranded — HR is the backstop so nothing rots silently.
	#    Scoped to the HR user's companies, exactly like every other HR branch in
	#    this file: this is the one route that reads rows the user was not named
	#    on, so without it an HR Manager permitted only on "Acme India" would see
	#    (and be allowed to approve) "Acme Singapore" tasks.
	stranded: set[str] = set()
	if _is_hr_user(user):
		scope = _hr_company_scope(user)
		hr_base = {**base}
		if scope is not None:
			hr_base["company"] = ("in", scope)

		unrouted = {**hr_base, "approver_user": ("is", "not set")}
		if has_role_field:
			unrouted["approver_role"] = ("is", "not set")
		_collect(unrouted)

		# "Stranded" = nominally routed, but no candidate approver can actually
		# act — they are the doer (leave-cover delegation hands the task to the
		# very manager who was its approver), or their account is disabled, or
		# the role has no other holder. The SoD gate would refuse all of them, so
		# without this the instance is invisible in every usable inbox.
		#
		# Bounded and bulk-resolved: one query for the candidates, then one each
		# for their employees / role holders / enabled accounts — not two lookups
		# per row, on a screen that HR (and every System Manager) loads often.
		#
		# OLDEST first, unlike every other query here: if the cap ever bites, the
		# rows worth surfacing are the ones stuck longest, not this morning's.
		# (The finished list is re-sorted newest-first below.)
		candidates = [
			r
			for r in frappe.get_all(
				"Goal",
				filters=hr_base,
				fields=fields,
				order_by="submitted_at asc",
				limit=_STRANDED_SWEEP_LIMIT,
			)
			if r.name not in collected
		]
		if candidates:
			doer_map = _bulk_doer_users(candidates)
			role_holders = _bulk_role_holders(
				{r.get("approver_role") for r in candidates if r.get("approver_role")}
			)
			enabled = _enabled_users(
				{r.get("approver_user") for r in candidates}
				| {u for holders in role_holders.values() for u in holders}
			)
			for r in candidates:
				if not _routed_from_maps(r, doer_map[r.name], role_holders, enabled):
					collected[r.name] = r
					stranded.add(r.name)

	# Never show someone their own work to approve — the gate would refuse it, so
	# listing it is a dead-end that also inflates the pending count. Doers are
	# resolved for the whole set at once.
	all_doers = _bulk_doer_users(list(collected.values()))
	rows = [(r, all_doers[r.name]) for r in collected.values() if user not in all_doers[r.name]]
	rows.sort(key=lambda pair: str(pair[0].get("submitted_at") or ""), reverse=True)
	out = []
	for r, doers in rows:
		# Flag the backstop case so HR can see WHY it landed with them: never
		# routed at all, or routed only to people who cannot act. Read off the
		# sweep's result rather than re-deriving it per row.
		unrouted = r.name in stranded or not (r.get("approver_user") or r.get("approver_role"))
		out.append(
			{
				"doctype": "Goal",
				"name": r.name,
				"category": "Task",
				"title": _("Task: {0}").format(r.goal_name),
				"subtitle": r.period_label or "",
				"employee": r.employee,
				"employee_name": r.employee_name,
				"date": str(getdate(r.submitted_at)) if r.submitted_at else None,
				# Full timestamp so several same-day submissions still sort newest-first.
				"_ts": str(r.submitted_at) if r.submitted_at else None,
				"unrouted": 1 if unrouted else 0,
				"action_type": "workflow",
			}
		)
	return out


def _pending_resignation_approvals(user: str) -> list[dict]:
	"""Resignations awaiting action. Two paths surface here:

	  * Reporting managers see their direct reports' rows in
	    'Pending Manager Acknowledgement'.
	  * HR users see ALL rows in 'Pending HR Approval' (final approve step).

	A single user holding both hats (reporting manager + HR Manager) sees both.
	"""
	collected: list[dict] = []
	reports = _resignation_reports_to_user(user)

	if reports:
		collected.extend(
			frappe.get_all(
				"Resignation Request",
				filters={
					"workflow_state": "Pending Manager Acknowledgement",
					"employee": ("in", list(reports)),
				},
				fields=[
					"name",
					"employee",
					"employee_name",
					"intended_last_working_date",
					"submission_date",
					"workflow_state",
				],
				order_by="submission_date desc",
			)
		)

	if _is_hr_user(user):
		hr_filters: dict = {"workflow_state": "Pending HR Approval"}
		scope = _hr_company_scope(user)
		if scope is not None:
			# Resignation Request has no direct company field — resolve via employee.
			emps_in_scope = frappe.get_all(
				"Employee",
				filters={"company": ("in", scope)},
				pluck="name",
			)
			if not emps_in_scope:
				emps_in_scope = ["__none__"]
			hr_filters["employee"] = ("in", emps_in_scope)
		collected.extend(
			frappe.get_all(
				"Resignation Request",
				filters=hr_filters,
				fields=[
					"name",
					"employee",
					"employee_name",
					"intended_last_working_date",
					"submission_date",
					"workflow_state",
				],
				order_by="submission_date desc",
			)
		)

	# De-dupe by name (HR Manager who is also someone's reporting manager).
	seen = set()
	rows = []
	for r in collected:
		if r.name in seen:
			continue
		seen.add(r.name)
		rows.append(r)

	out = []
	for r in rows:
		stage = (
			_("Acknowledge")
			if r.workflow_state == "Pending Manager Acknowledgement"
			else _("HR Approve")
		)
		out.append(
			{
				"doctype": "Resignation Request",
				"name": r.name,
				"category": "Resignation",
				"title": _("Resignation — {0}").format(stage),
				"subtitle": _("Last working day: {0}").format(r.intended_last_working_date)
				if r.intended_last_working_date
				else _("Last working day: —"),
				"employee": r.employee,
				"employee_name": r.employee_name,
				"date": str(r.submission_date) if r.submission_date else None,
				"action_type": "workflow",
			}
		)
	return out


def _pending_profile_change_approvals(user: str) -> list[dict]:
	"""Employee Profile Change Requests awaiting HR review. Visible to anyone
	holding an HR role (the doctype permission gate). Approval = apply the
	requested field changes to the Employee record."""
	if not _is_hr_user(user):
		return []
	filters: dict = {"status": "Submitted"}
	scope = _hr_company_scope(user)
	if scope is not None:
		filters["company"] = ("in", scope)
	rows = frappe.get_all(
		"Employee Profile Change Request",
		filters=filters,
		fields=["name", "employee", "employee_name", "company", "submitted_at"],
		order_by="submitted_at desc",
	)
	out = []
	for r in rows:
		count = frappe.db.count("Employee Profile Change Item", {"parent": r.name})
		out.append(
			{
				"doctype": "Employee Profile Change Request",
				"name": r.name,
				"category": "Profile Update",
				"title": _("Profile update — {0} field(s)").format(count),
				"subtitle": _("Company: {0}").format(r.company or "—"),
				"employee": r.employee,
				"employee_name": r.employee_name,
				"date": str(getdate(r.submitted_at)) if r.submitted_at else None,
				"action_type": "status",
			}
		)
	return out


def _pending_onboarding_approvals(user: str) -> list[dict]:
	"""Employee Onboarding Applications in 'Pending Verification' awaiting HR
	review. Approve = mark Verified (auto-tick the checklist boxes since the
	HR user reviewed in-app); reject = mark Rejected with the comment as
	rejection_reason. New-hire conversion still happens on the Desk page
	because it needs salary + slabs."""
	if not _is_hr_user(user):
		return []
	filters: dict = {"status": "Pending Verification"}
	scope = _hr_company_scope(user)
	if scope is not None:
		filters["target_company"] = ("in", scope)
	rows = frappe.get_all(
		"Employee Onboarding Application",
		filters=filters,
		fields=[
			"name",
			"first_name",
			"last_name",
			"personal_email",
			"target_company",
			"target_designation",
			"submitted_on",
		],
		order_by="submitted_on desc",
	)
	out = []
	for r in rows:
		full_name = " ".join(p for p in (r.first_name, r.last_name) if p)
		out.append(
			{
				"doctype": "Employee Onboarding Application",
				"name": r.name,
				"category": "Onboarding",
				"title": _("Onboarding: {0}").format(full_name or r.personal_email or r.name),
				"subtitle": _("{0} → {1}").format(
					r.target_company or "—", r.target_designation or "—"
				),
				"employee": "",
				"employee_name": full_name,
				"date": str(getdate(r.submitted_on)) if r.submitted_on else None,
				"action_type": "status",
			}
		)
	return out


def _pending_grievance_approvals(user: str) -> list[dict]:
	"""Open Employee Grievances awaiting HR triage. Approve = mark Investigated
	(intermediate acknowledgement — the full Resolved transition needs more
	fields and is done on the Grievance form). Reject = mark Invalid."""
	if not _is_hr_user(user):
		return []
	filters: dict = {"status": "Open"}
	scope = _hr_company_scope(user)
	if scope is not None:
		# Grievance has no `company` column directly — resolve via raised_by.
		emps_in_scope = frappe.get_all(
			"Employee",
			filters={"company": ("in", scope)},
			pluck="name",
		)
		if not emps_in_scope:
			return []
		filters["raised_by"] = ("in", emps_in_scope)
	rows = frappe.get_all(
		"Employee Grievance",
		filters=filters,
		fields=["name", "raised_by", "employee_name", "subject", "date"],
		order_by="date desc",
	)
	out = []
	for r in rows:
		out.append(
			{
				"doctype": "Employee Grievance",
				"name": r.name,
				"category": "Grievance",
				"title": _("Grievance: {0}").format(r.subject or "—"),
				"subtitle": _("Open since {0}").format(getdate(r.date)) if r.date else "",
				"employee": r.raised_by,
				"employee_name": r.employee_name,
				"date": str(getdate(r.date)) if r.date else None,
				"action_type": "status",
			}
		)
	return out


_APPROVAL_PROVIDERS = (
	_pending_leave_approvals,
	_pending_expense_approvals,
	_pending_advance_approvals,
	_pending_shift_approvals,
	_pending_attendance_approvals,
	_pending_task_approvals,
	_pending_resignation_approvals,
	_pending_profile_change_approvals,
	_pending_onboarding_approvals,
	_pending_grievance_approvals,
)


@frappe.whitelist()
def hr_withdraw_resignation(name: str, comment: str) -> dict:
	"""HR-only: undo an already-Approved resignation (workflow supports the
	transition). Used when an exit is called off after the formal approval.
	Comment is mandatory — the audit trail needs the reason.
	"""
	if not (comment and strip_html(comment).strip()):
		frappe.throw(_("A comment explaining the withdrawal is required."))

	from frappe.model.workflow import apply_workflow, get_transitions

	doc = frappe.get_doc("Resignation Request", name)
	_assert_hr_role("resignation request")
	if doc.get("workflow_state") != "Approved":
		frappe.throw(
			_("Only Approved resignations can be withdrawn by HR (currently {0}).").format(
				doc.get("workflow_state")
			)
		)
	actions = {t.get("action") for t in get_transitions(doc)}
	if "Withdraw" not in actions:
		frappe.throw(_("The Withdraw transition is not available from the current state."))

	apply_workflow(doc, "Withdraw")
	doc = frappe.get_doc("Resignation Request", name)
	_add_comment_if_any(doc, comment)
	frappe.db.commit()

	# Refresh the resigning employee's exit dashboard + every HR inbox.
	emp_user = frappe.db.get_value("Employee", doc.employee, "user_id")
	if emp_user:
		_refresh_requester("Resignation Request", emp_user)
	_broadcast_hr_inbox_refresh()
	return {"name": doc.name, "workflow_state": doc.get("workflow_state")}


@frappe.whitelist()
def get_pending_approvals() -> list[dict]:
	"""Unified inbox of every request awaiting the current user's action as an
	approver (Leave, Expense, Advance, Shift, Attendance, Task Instance,
	Resignation). Flat list, newest first."""
	user = frappe.session.user
	items: list[dict] = []
	for provider in _APPROVAL_PROVIDERS:
		try:
			items.extend(provider(user))
		except Exception:
			frappe.log_error(
				title=f"Pending approvals provider failed: {provider.__name__}",
				message=frappe.get_traceback(),
			)
	# Newest first. Prefer the full timestamp where a provider supplies one so
	# same-day items don't tie arbitrarily ("_ts" starts with the date, so it
	# compares correctly against date-only values).
	items.sort(key=lambda i: (i.get("_ts") or i.get("date") or ""), reverse=True)
	return items


@frappe.whitelist()
def get_approvals_summary() -> dict:
	"""Per-category counts (+ total) for the inbox header badges."""
	items = get_pending_approvals()
	counts = {cat: 0 for cat in _APPROVAL_CATEGORIES}
	for item in items:
		cat = item.get("category")
		if cat in counts:
			counts[cat] += 1
	counts["total"] = len(items)
	return counts


def _assert_leave_approver(doc):
	user = frappe.session.user
	if doc.leave_approver != user:
		frappe.throw(_("You are not the approver for this leave application."), frappe.PermissionError)
	if doc.employee in _approver_employees_for_user(user) and frappe.db.get_single_value(
		"HR Settings", "prevent_self_leave_approval"
	):
		frappe.throw(_("You cannot approve your own leave application."), frappe.PermissionError)


def _assert_expense_approver(doc):
	if doc.expense_approver != frappe.session.user:
		frappe.throw(_("You are not the approver for this expense claim."), frappe.PermissionError)


def _assert_shift_approver(doc):
	if doc.approver != frappe.session.user:
		frappe.throw(_("You are not the approver for this shift request."), frappe.PermissionError)


def _assert_reports_to_approver(doc, label: str):
	"""For doctypes without an explicit approver field (Advance, Attendance,
	Resignation) — the authority is the employee's reporting manager."""
	if doc.employee not in _resignation_reports_to_user(frappe.session.user):
		frappe.throw(_("You are not the approver for this {0}.").format(label), frappe.PermissionError)


def _assert_attendance_approver(doc):
	"""Attendance Requests may be actioned by the employee's reporting manager
	OR by HR. HR handled these before there was any approval flow (they were the
	ones submitting/deleting requests), so they must keep that authority —
	especially on Desk, where HR, not the manager, does the work."""
	if _is_hr_user(frappe.session.user):
		return
	if doc.employee not in _resignation_reports_to_user(frappe.session.user):
		frappe.throw(
			_("Only the employee's reporting manager or HR can action this attendance request."),
			frappe.PermissionError,
		)


def _task_doer_users(doc) -> set[str]:
	"""Every user who could be considered to have DONE this task.

	The submitter is the strongest signal; the assigned employee and (for
	leave-cover) the recorded performer are included so re-routing the
	instance can't launder a self-approval.
	"""
	users: set[str] = set()
	if doc.get("submitted_by"):
		users.add(doc.submitted_by)
	for field in ("employee", "performed_by"):
		emp = doc.get(field)
		if emp:
			user = frappe.db.get_value("Employee", emp, "user_id")
			if user:
				users.add(user)
	return users


def _assert_task_approver(doc):
	"""Gate a task-completion decision.

	Two independent checks:

	  * IDENTITY — you must be the routed approver, a holder of the routed
	    approver role, or HR. HR can always step in, which is what stops an
	    unroutable instance from deadlocking.
	  * SEGREGATION OF DUTIES — you may never approve work you performed.
	    This one has NO exception, not even for HR: an approval by the doer is
	    not an approval, and the Critical tier's entire value is this rule.
	"""
	if doc.goal_type != "Task Instance":
		frappe.throw(_("This is not a task instance."), frappe.PermissionError)

	user = frappe.session.user
	role_ok = bool(doc.get("approver_role")) and doc.approver_role in frappe.get_roles(user)

	# HR may step in for anything, but ONLY within their companies — otherwise the
	# company scoping on the inbox is cosmetic: an HR user restricted to "Acme
	# India" could still approve an "Acme Singapore" instance by passing its name
	# (Goal names are sequential and guessable). Named approver / role holder are
	# already self-scoping — they were put on this specific instance.
	is_hr_in_scope = False
	if _is_hr_user(user):
		scope = _hr_company_scope(user)
		is_hr_in_scope = scope is None or doc.get("company") in scope

	if not (doc.get("approver_user") == user or role_ok or is_hr_in_scope):
		frappe.throw(_("You are not the approver for this task."), frappe.PermissionError)

	if user in _task_doer_users(doc):
		frappe.throw(
			_(
				"You cannot approve a task you performed yourself. Someone other than the "
				"doer must approve it — ask your manager or HR to review it."
			),
			frappe.PermissionError,
		)


def _assert_hr_role(label: str):
	if not _is_hr_user(frappe.session.user):
		frappe.throw(
			_("Only HR users can approve / reject a {0}.").format(label),
			frappe.PermissionError,
		)


def _validate_approver(doc) -> None:
	"""Authorization gate: raises PermissionError unless the current user is the
	legitimate approver for ``doc``. Called by both approve and reject."""
	dt = doc.doctype
	if dt == "Leave Application":
		_assert_leave_approver(doc)
	elif dt == "Expense Claim":
		_assert_expense_approver(doc)
	elif dt == "Shift Request":
		_assert_shift_approver(doc)
	elif dt == "Employee Advance":
		_assert_reports_to_approver(doc, "advance")
	elif dt == "Attendance Request":
		_assert_attendance_approver(doc)
	elif dt == "Resignation Request":
		# Two valid approvers depending on the workflow state:
		#  * Pending Manager Acknowledgement → the employee's reporting manager
		#  * Pending HR Approval            → any HR user
		state = doc.get("workflow_state")
		if state == "Pending HR Approval":
			_assert_hr_role("resignation request")
		else:
			_assert_reports_to_approver(doc, "resignation request")
	elif dt == "Goal":
		_assert_task_approver(doc)
	elif dt == "Employee Profile Change Request":
		_assert_hr_role("profile change request")
	elif dt == "Employee Onboarding Application":
		_assert_hr_role("onboarding application")
	elif dt == "Employee Grievance":
		_assert_hr_role("grievance")
	else:
		frappe.throw(_("Unsupported approval document type: {0}").format(dt))


def _add_comment_if_any(doc, comment: str | None) -> None:
	if comment:
		try:
			doc.add_comment("Comment", strip_html(comment).strip())
		except Exception:
			frappe.log_error(title="Approval comment failed", message=frappe.get_traceback())


# ---------------------------------------------------------------------------
# Org-wide attendance roll-call — "who's in, who's out, who's on leave"
# ---------------------------------------------------------------------------


def _attendance_scope_for_user(user: str) -> dict:
	"""Return {scope: 'all'|'team'|'none', companies: [..] | None, employees: set | None}.
	HR Manager / System Manager see all (optionally filtered by company).
	Reporting managers see their active direct reports only.
	Everyone else sees nothing.
	"""
	roles = set(frappe.get_roles(user))
	if {"HR Manager", "System Manager"} & roles:
		return {"scope": "all"}
	manager_emps = _approver_employees_for_user(user)
	if manager_emps:
		reports = set(
			frappe.get_all(
				"Employee",
				filters={"reports_to": ("in", manager_emps), "status": "Active"},
				pluck="name",
			)
		)
		return {"scope": "team", "employees": reports}
	return {"scope": "none"}


def _resolve_attendance_scope(user: str, scope: str) -> dict:
	"""Translate the public `scope` arg to the internal scope_dict.

	  - 'auto' → role-based (HR/SysMgr see all; reporting managers see team).
	  - 'team' → force the caller's direct reports even if they're HR.
	  - 'all'  → explicit whole-org; HR Manager / System Manager only.
	"""
	auto_scope = _attendance_scope_for_user(user)
	if scope == "team":
		reports = set(
			frappe.get_all(
				"Employee",
				filters={
					"reports_to": ("in", _approver_employees_for_user(user) or ["__none__"]),
					"status": "Active",
				},
				pluck="name",
			)
		)
		return {"scope": "team" if reports else "none", "employees": reports}
	if scope == "all":
		if {"HR Manager", "System Manager"} & set(frappe.get_roles(user)):
			return {"scope": "all"}
		return {"scope": "none"}
	return auto_scope


def _attendance_employee_universe(scope_dict: dict, company: str | None) -> list[dict]:
	"""Active Employees under the resolved scope (+ optional company filter)."""
	from indian_hrms_compliance.overrides.employee_master import exclude_virtual

	emp_filters = exclude_virtual({"status": "Active"})
	if scope_dict["scope"] == "team":
		emp_filters["name"] = ("in", list(scope_dict["employees"]) or [""])
	if company:
		emp_filters["company"] = company
	return frappe.get_all(
		"Employee",
		filters=emp_filters,
		fields=["name", "employee_name", "company", "department", "designation", "image", "user_id"],
		order_by="employee_name asc",
	)


def _make_card(emp: str, emp_index: dict, extras: dict | None = None) -> dict:
	base = emp_index.get(emp) or {}
	card = {
		"employee": emp,
		"employee_name": base.get("employee_name"),
		"company": base.get("company"),
		"department": base.get("department"),
		"designation": base.get("designation"),
		"image": base.get("image"),
	}
	if extras:
		card.update(extras)
	return card


def _today_buckets(
	scope_dict: dict, employees: list[dict], today_d
) -> dict:
	"""Live roll-call from Employee Checkin + Approved Leave Application.

	Used when the requested date IS today — the Attendance doctype rows for
	today are typically marked overnight by the scheduler, so we partition
	off raw check-ins instead.
	"""
	emp_index = {e["name"]: e for e in employees}
	emp_names = list(emp_index.keys())

	if not emp_names:
		return {
			"mode": "today",
			"in_now": [],
			"out": [],
			"on_leave": [],
			"not_yet_in": [],
			"counts": {"in_now": 0, "out": 0, "on_leave": 0, "not_yet_in": 0, "total": 0},
		}

	from indian_hrms_compliance.hr.doctype.employee_checkin.employee_checkin import (
		dedupe_rapid_checkins,
	)

	# Today's check-ins, oldest→newest per employee so we can collapse rapid
	# repeat swipes and reason about IN/OUT order.
	checkins = frappe.db.sql(
		"""
		SELECT employee, log_type, time
		FROM `tabEmployee Checkin`
		WHERE employee IN %(emps)s
		  AND DATE(time) = %(today)s
		ORDER BY employee, time ASC
		""",
		{"emps": tuple(emp_names) + ("__none__",), "today": today_d},
		as_dict=True,
	)
	punches_by_emp: dict[str, list] = {}
	for c in checkins:
		punches_by_emp.setdefault(c["employee"], []).append(c)

	dup_window = cint(frappe.db.get_single_value("HR Settings", "duplicate_checkin_window_minutes"))

	# Approved Leave Applications covering today.
	on_leave_rows = frappe.db.sql(
		"""
		SELECT employee, leave_type, half_day
		FROM `tabLeave Application`
		WHERE employee IN %(emps)s
		  AND status = 'Approved'
		  AND docstatus = 1
		  AND from_date <= %(today)s
		  AND to_date   >= %(today)s
		""",
		{"emps": tuple(emp_names) + ("__none__",), "today": today_d},
		as_dict=True,
	)
	leave_by_emp = {r["employee"]: r for r in on_leave_rows}

	in_now: list[dict] = []
	out: list[dict] = []
	on_leave: list[dict] = []
	not_yet_in: list[dict] = []

	for emp in emp_names:
		punches = punches_by_emp.get(emp)
		# Collapse accidental rapid repeat swipes before reasoning about
		# IN/OUT, mirroring how attendance itself is finalised.
		punches = dedupe_rapid_checkins(punches, dup_window) if punches else []
		first_in = next(
			(str(p["time"]) for p in punches if (p["log_type"] or "").upper() == "IN"), None
		)
		# Fall back to the earliest punch when the device sends no IN tag.
		first_in = first_in or (str(punches[0]["time"]) if punches else None)

		lv = leave_by_emp.get(emp)
		if lv:
			on_leave.append(
				_make_card(
					emp,
					emp_index,
					{
						"leave_type": lv["leave_type"],
						"half_day": int(lv["half_day"] or 0),
						"first_in": first_in,
					},
				)
			)
			continue
		if not punches:
			not_yet_in.append(_make_card(emp, emp_index))
			continue

		last = punches[-1]
		last_lt = (last["log_type"] or "").upper()
		if last_lt == "IN":
			currently_in = True
		elif last_lt == "OUT":
			currently_in = False
		else:
			# Biometric devices that don't tag IN/OUT: punches alternate
			# (1st = IN, 2nd = OUT, ...), so an odd number of de-duplicated
			# punches means the person is currently in. A lone punch reads as
			# In for the day, not Out.
			currently_in = (len(punches) % 2) == 1

		extras = {
			"first_in": first_in,
			"last_action": last["log_type"] or ("IN" if currently_in else "OUT"),
			"last_time": str(last["time"]),
		}
		if currently_in:
			in_now.append(_make_card(emp, emp_index, extras))
		else:
			out.append(_make_card(emp, emp_index, extras))

	return {
		"mode": "today",
		"in_now": in_now,
		"out": out,
		"on_leave": on_leave,
		"not_yet_in": not_yet_in,
		"counts": {
			"in_now": len(in_now),
			"out": len(out),
			"on_leave": len(on_leave),
			"not_yet_in": len(not_yet_in),
			"total": len(employees),
		},
	}


# Attendance.status → bucket key used in past-date mode.
_ATTENDANCE_STATUS_TO_BUCKET = {
	"Present": "present",
	"Work From Home": "present",
	"Half Day": "on_leave",
	"On Leave": "on_leave",
	"Absent": "absent",
}


def _past_buckets(
	scope_dict: dict, employees: list[dict], for_date
) -> dict:
	"""Past-date roll-call from submitted Attendance rows + a leave fallback.

	Buckets:
	  - present  : Attendance.status in ('Present', 'Work From Home')
	  - on_leave : Attendance.status in ('On Leave', 'Half Day') OR an Approved
	               Leave Application covers for_date (catches rows that were
	               never marked because the employee was on leave the whole day)
	  - absent   : Attendance.status == 'Absent'
	  - not_marked : Active Employees with neither Attendance nor leave for the date
	"""
	emp_index = {e["name"]: e for e in employees}
	emp_names = list(emp_index.keys())

	if not emp_names:
		return {
			"mode": "past",
			"present": [],
			"on_leave": [],
			"absent": [],
			"not_marked": [],
			"counts": {"present": 0, "on_leave": 0, "absent": 0, "not_marked": 0, "total": 0},
		}

	att_rows = frappe.db.sql(
		"""
		SELECT employee, status, in_time, out_time, working_hours, leave_type
		FROM `tabAttendance`
		WHERE employee IN %(emps)s
		  AND attendance_date = %(d)s
		  AND docstatus = 1
		""",
		{"emps": tuple(emp_names) + ("__none__",), "d": for_date},
		as_dict=True,
	)
	att_by_emp = {r["employee"]: r for r in att_rows}

	# Leave fallback for the same day — employees on Approved Leave often
	# never get an Attendance row (the leave covers it).
	leave_rows = frappe.db.sql(
		"""
		SELECT employee, leave_type, half_day
		FROM `tabLeave Application`
		WHERE employee IN %(emps)s
		  AND status = 'Approved'
		  AND docstatus = 1
		  AND from_date <= %(d)s
		  AND to_date   >= %(d)s
		""",
		{"emps": tuple(emp_names) + ("__none__",), "d": for_date},
		as_dict=True,
	)
	leave_by_emp = {r["employee"]: r for r in leave_rows}

	present: list[dict] = []
	on_leave: list[dict] = []
	absent: list[dict] = []
	not_marked: list[dict] = []

	for emp in emp_names:
		att = att_by_emp.get(emp)
		if att:
			bucket = _ATTENDANCE_STATUS_TO_BUCKET.get(att["status"])
			extras = {
				"status": att["status"],
				"in_time": str(att["in_time"]) if att["in_time"] else None,
				"out_time": str(att["out_time"]) if att["out_time"] else None,
				"working_hours": flt(att["working_hours"] or 0),
				"leave_type": att.get("leave_type") or "",
			}
			card = _make_card(emp, emp_index, extras)
			if bucket == "present":
				present.append(card)
			elif bucket == "on_leave":
				on_leave.append(card)
			elif bucket == "absent":
				absent.append(card)
			else:
				# Unknown status — treat as not_marked rather than silently dropping.
				not_marked.append(card)
			continue
		# No Attendance row — check leave fallback.
		lv = leave_by_emp.get(emp)
		if lv:
			on_leave.append(
				_make_card(
					emp,
					emp_index,
					{
						"status": "On Leave",
						"leave_type": lv["leave_type"],
						"half_day": int(lv["half_day"] or 0),
					},
				)
			)
			continue
		not_marked.append(_make_card(emp, emp_index))

	return {
		"mode": "past",
		"present": present,
		"on_leave": on_leave,
		"absent": absent,
		"not_marked": not_marked,
		"counts": {
			"present": len(present),
			"on_leave": len(on_leave),
			"absent": len(absent),
			"not_marked": len(not_marked),
			"total": len(employees),
		},
	}


@frappe.whitelist()
def get_org_attendance_today(
	company: str | None = None,
	scope: str = "auto",
	for_date: str | None = None,
) -> dict:
	"""Org-wide attendance roll-call. Two modes, picked by ``for_date``:

	  * **Today (default)** — live partition off raw Employee Checkin +
	    Approved Leave Application. Buckets: in_now / out / on_leave / not_yet_in.
	    Attendance for today is normally only marked overnight by the scheduler,
	    so we can't rely on it for an "as-of-now" view.

	  * **Past date** — partition off the submitted Attendance doctype, with
	    leave applications as a fallback for employees who never got an
	    Attendance row because the leave covered the day. Buckets:
	    present / absent / on_leave / not_marked.

	Scope:
	  - 'auto' (default) — HR Manager / System Manager see the whole org;
	    reporting managers see only their direct reports; everyone else gets
	    an empty payload.
	  - 'team' — restrict to the caller's direct reports even if they also
	    hold an HR role.
	  - 'all'  — explicit whole-org view; requires HR Manager / System Manager.

	Optional ``company`` narrows the universe further. ``for_date`` accepts an
	ISO date string ('2026-06-01') and defaults to today.
	"""
	user = frappe.session.user
	scope_dict = _resolve_attendance_scope(user, scope)

	today_d = getdate()
	requested_date = getdate(for_date) if for_date else today_d
	if requested_date > today_d:
		# Future dates make no sense for a "what's actually happening" view.
		# Fall through to today rather than throwing — friendlier UX.
		requested_date = today_d

	if scope_dict["scope"] == "none":
		empty_today = {
			"mode": "today",
			"in_now": [], "out": [], "on_leave": [], "not_yet_in": [],
			"counts": {"in_now": 0, "out": 0, "on_leave": 0, "not_yet_in": 0, "total": 0},
		}
		empty_past = {
			"mode": "past",
			"present": [], "absent": [], "on_leave": [], "not_marked": [],
			"counts": {"present": 0, "absent": 0, "on_leave": 0, "not_marked": 0, "total": 0},
		}
		buckets = empty_today if requested_date == today_d else empty_past
		return {
			"as_of": str(now_datetime()),
			"for_date": str(requested_date),
			"scope": "none",
			"company_filter": company or "",
			**buckets,
		}

	employees = _attendance_employee_universe(scope_dict, company)

	if requested_date == today_d:
		buckets = _today_buckets(scope_dict, employees, today_d)
	else:
		buckets = _past_buckets(scope_dict, employees, requested_date)

	return {
		"as_of": str(now_datetime()),
		"for_date": str(requested_date),
		"scope": scope_dict["scope"],
		"company_filter": company or "",
		**buckets,
	}


_APPROVAL_DOCTYPES = (
	"Leave Application",
	"Expense Claim",
	"Employee Advance",
	"Shift Request",
	"Attendance Request",
	"Resignation Request",
	"Goal",
	"Employee Profile Change Request",
	"Employee Onboarding Application",
	"Employee Grievance",
)

# Inbox doctypes whose own controllers already raise a PWA Notification to the
# requester on an approve/reject decision (Leave/Expense/Shift via the mixin,
# Profile Change via its bespoke helper). Skip these in the generic notifier
# below so the requester isn't told twice.
_SELF_NOTIFIES_ON_DECISION = frozenset(
	{
		"Leave Application",
		"Expense Claim",
		"Shift Request",
		"Employee Profile Change Request",
	}
)

# (doctype, approved?) -> past-tense phrase used in the requester's notification.
# Falls back to a plain "approved"/"rejected" for anything not listed.
_DECISION_PHRASE = {
	("Goal", False): "sent back for changes",
	("Employee Onboarding Application", True): "verified",
	("Employee Grievance", True): "acknowledged and is now under investigation",
	("Employee Grievance", False): "reviewed and marked invalid",
}


def _requester_user(doctype: str, doc) -> str | None:
	"""Resolve the requesting person's User for an inbox doc. Grievance keys off
	`raised_by` (an Employee link); everything else off `employee`."""
	emp = doc.get("raised_by") if doctype == "Employee Grievance" else doc.get("employee")
	if not emp:
		return None
	return frappe.db.get_value("Employee", emp, "user_id")


def _notify_requester_decision(
	doctype: str,
	name: str,
	requester_user: str | None,
	approved: bool,
	comment: str | None = None,
	state: str | None = None,
) -> None:
	"""Raise a PWA Notification telling the requester their inbox item was
	approved/rejected. No-op for doctypes that already self-notify, when the
	actor IS the requester, or when no User can be resolved (e.g. a pre-hire
	onboarding applicant who has no login yet). `state` is the resulting
	workflow_state, used to word multi-stage transitions accurately."""
	if doctype in _SELF_NOTIFIES_ON_DECISION:
		return
	from_user = frappe.session.user
	if not requester_user or requester_user == from_user:
		return

	from frappe import bold

	if doctype == "Resignation Request" and approved:
		# "Approve" here can be the intermediate manager Acknowledge (hands off to
		# HR) rather than the final approval — don't tell the employee it's
		# approved until it actually is.
		phrase = "approved" if state == "Approved" else "acknowledged and forwarded to HR"
	else:
		phrase = _DECISION_PHRASE.get((doctype, bool(approved)), "approved" if approved else "rejected")
	from_name = frappe.db.get_value("User", from_user, "full_name", cache=True) or from_user

	# "Your Goal HR-GOAL-2026-00042" is meaningless to an employee — a task
	# instance is a "Task", and its own name is far more use than its ID.
	label, subject = doctype, name
	if doctype == "Goal":
		label = "Task"
		subject = frappe.db.get_value("Goal", name, "goal_name") or name

	message = f"Your {bold(label)} {subject} has been {bold(phrase)} by {bold(from_name)}"
	reason = strip_html(comment).strip() if comment else ""
	if reason:
		message += f": {reason}"

	try:
		frappe.get_doc(
			{
				"doctype": "PWA Notification",
				"from_user": from_user,
				"to_user": requester_user,
				"message": message,
				"reference_document_type": doctype,
				"reference_document_name": name,
			}
		).insert(ignore_permissions=True)
	except Exception:
		# The decision itself is the source of truth — never let a failed
		# notification roll back an approve/reject.
		frappe.log_error(f"PWA decision notification failed: {doctype} {name}")


def notify_approver_of_new_request(doc, method: str | None = None) -> None:
	"""doc_events after_insert hook: tell the employee's reporting manager that a
	new request awaits action. Covers the doctypes (Attendance Request, Employee
	Advance, Resignation Request) that lack the Leave/Expense/Shift approver
	notification. Best-effort — never blocks the insert."""
	try:
		emp = doc.get("employee")
		if not emp:
			return
		reports_to = frappe.db.get_value("Employee", emp, "reports_to")
		manager_user = (
			frappe.db.get_value("Employee", reports_to, "user_id") if reports_to else None
		)
		from_user = frappe.session.user
		if not manager_user or manager_user == from_user:
			return

		from frappe import bold

		emp_name = doc.get("employee_name") or emp
		message = f"{bold(emp_name)} raised a new {bold(doc.doctype)} for your approval: {doc.name}"
		frappe.get_doc(
			{
				"doctype": "PWA Notification",
				"from_user": from_user,
				"to_user": manager_user,
				"message": message,
				"reference_document_type": doc.doctype,
				"reference_document_name": doc.name,
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			f"PWA new-request notification failed: "
			f"{getattr(doc, 'doctype', '?')} {getattr(doc, 'name', '?')}"
		)


@frappe.whitelist()
def approve_request(doctype: str, name: str, comment: str | None = None) -> dict:
	"""Approve one inbox item. Re-derives and enforces approver authorization
	server-side before acting, then applies the correct approval mechanic for
	the doctype."""
	if doctype not in _APPROVAL_DOCTYPES:
		frappe.throw(_("Unsupported approval document type: {0}").format(doctype))

	doc = frappe.get_doc(doctype, name)
	_validate_approver(doc)
	# Capture the requester's User up front — some branches delete the doc.
	requester_user = _requester_user(doctype, doc)

	if doctype == "Leave Application":
		doc.status = "Approved"
		doc.save(ignore_permissions=True)
		if doc.docstatus == 0:
			doc.submit()
	elif doctype == "Expense Claim":
		doc.approval_status = "Approved"
		doc.save(ignore_permissions=True)
		if doc.docstatus == 0:
			doc.submit()
	elif doctype == "Shift Request":
		doc.status = "Approved"
		doc.save(ignore_permissions=True)
		if doc.docstatus == 0:
			doc.submit()
	elif doctype == "Attendance Request":
		if doc.docstatus != 0:
			frappe.throw(_("This Attendance Request is not pending approval."))
		if frappe.get_meta(doctype).has_field("status"):
			doc.status = "Approved"
		# Approval must not be blocked just because there's nothing to create
		# (attendance already in the requested status / holiday / on leave). The
		# manager is endorsing the request; create_attendance_records() skips
		# days with nothing to do.
		doc.flags.ignore_no_attendance_to_create = True
		# The controller emits Desk-style info msgprints while creating/updating
		# attendance ("Updated status from Absent to Present …", "Attendance not
		# submitted … Holiday"). In the PWA those surface as scary error toasts.
		# Mute them for the API path — real exceptions (frappe.throw) still raise.
		_muted = frappe.flags.mute_messages
		frappe.flags.mute_messages = True
		try:
			# Submission = approval → creates the Attendance records.
			doc.submit()
		finally:
			frappe.flags.mute_messages = _muted
	elif doctype == "Employee Advance":
		# No approval status — approval = submission of the request.
		if doc.docstatus == 0:
			doc.submit()
	elif doctype == "Goal":
		# Approve the task-instance completion. Stamping WHO approved and WHEN is
		# the whole point of an approval control — without it the record proves
		# only that a status changed, which is not evidence anybody can audit.
		# Only a submitted, undecided instance can be approved — this blocks
		# double-approval and approving work nobody has done yet. Tolerates a
		# site where submitted_at hasn't synced rather than blocking every approval.
		awaiting = doc.status == "In Progress" and (
			not doc.meta.has_field("submitted_at") or doc.get("submitted_at")
		)
		if not awaiting:
			frappe.throw(_("This task is not awaiting approval."))
		doc.status = "Completed"
		doc.progress = 100
		for field, value in (
			("approved_by", frappe.session.user),
			("approved_at", now_datetime()),
			("approval_notes", strip_html(comment).strip() if comment else None),
		):
			if doc.meta.has_field(field):
				doc.set(field, value)
		doc.flags.ihc_governed_write = True
		doc.save(ignore_permissions=True)
		# An approval-gated distributed child reaches Completed HERE (not in
		# complete_task_instance), so the parent rollup must fire here too —
		# otherwise the head's Accountable instance would hang forever.
		if doc.get("accountable_parent"):
			_maybe_complete_accountable_parent(doc.accountable_parent)
	elif doctype == "Resignation Request":
		from frappe.model.workflow import apply_workflow, get_transitions

		# Dispatch the right transition based on the current state:
		#  * Pending Manager Acknowledgement → "Acknowledge" (manager hand-off to HR)
		#  * Pending HR Approval            → "Approve" (final)
		actions = {t.get("action") for t in get_transitions(doc)}
		state = doc.get("workflow_state")
		if state == "Pending HR Approval" and "Approve" in actions:
			apply_workflow(doc, "Approve")
		elif "Acknowledge" in actions:
			apply_workflow(doc, "Acknowledge")
		elif "Approve" in actions:
			apply_workflow(doc, "Approve")
		else:
			frappe.throw(
				_("No approval transition is available from state {0}.").format(state)
			)
	elif doctype == "Employee Profile Change Request":
		from indian_hrms_compliance.hr.doctype.employee_profile_change_request.employee_profile_change_request import (
			approve_profile_change_request,
		)

		approve_profile_change_request(name, comment=comment)
		# Re-read so the rest of this function sees the updated state.
		doc = frappe.get_doc(doctype, name)
	elif doctype == "Employee Onboarding Application":
		# Approve = "Mark Verified", but ONLY if every checklist box is already
		# ticked. The PWA can't replace the document-by-document verification
		# step; HR must do it on the Desk form (where the uploaded copies are
		# viewable) BEFORE coming back to the inbox. This stops a one-tap
		# approval from masquerading as a full PAN/Aadhaar/bank/photo check.
		missing = [
			lbl
			for fname, lbl in (
				("pan_verified", "PAN"),
				("aadhaar_verified", "Aadhaar"),
				("bank_verified", "Bank A/c"),
				("photo_verified", "Photo"),
			)
			if not doc.get(fname)
		]
		if missing:
			frappe.throw(
				_(
					"Open the application on Desk and tick the verification checklist (PAN / Aadhaar / Bank / Photo) before approving. Missing: {0}."
				).format(", ".join(missing)),
				title=_("Verification Required"),
			)

		doc.status = "Verified"
		if not doc.verified_by:
			doc.verified_by = frappe.session.user
		if not doc.verified_on:
			doc.verified_on = now_datetime()
		doc.save(ignore_permissions=True)
	elif doctype == "Employee Grievance":
		# "Approve" = acknowledge / mark Investigated. The doctype's own
		# validation requires `cause_of_grievance` when status moves to
		# Investigated, so the inbox comment becomes that field. We REQUIRE
		# a comment for grievance approval; this both unblocks save and
		# leaves a meaningful audit trail.
		if not (comment and strip_html(comment).strip()):
			frappe.throw(
				_("A short investigation note is required to mark a grievance Investigated."),
				title=_("Note Required"),
			)
		doc.status = "Investigated"
		if not doc.cause_of_grievance:
			doc.cause_of_grievance = comment
		doc.save(ignore_permissions=True)

	_add_comment_if_any(doc, comment)
	# Notify the requester their item was approved (skips the doctypes whose own
	# controllers already do — Leave/Expense/Shift/Profile Change).
	_notify_requester_decision(
		doctype, name, requester_user, approved=True, comment=comment, state=doc.get("workflow_state")
	)
	frappe.db.commit()

	# Live-refresh: the approver's inbox (so the row drops off) AND, where the
	# action has a visible employee-side effect, the requester's resources.
	_pwa_refetch(list(_INBOX_CACHE_KEYS), user=frappe.session.user)
	emp_field = doc.get("employee") or doc.get("raised_by")
	if emp_field:
		req_user = frappe.db.get_value("Employee", emp_field, "user_id")
		_refresh_requester(doctype, req_user)
	if doctype == "Resignation Request" and doc.get("workflow_state") == "Pending HR Approval":
		# Stage shifted from Manager Ack → HR Approval — other HR users should
		# see the row appear in their inbox too.
		_broadcast_hr_inbox_refresh()
	elif doctype == "Goal":
		# One task instance can sit in several inboxes at once (role-routed, HR
		# backstop). Now that it's decided, drop it from the OTHER reviewers'
		# cached inboxes too — the server already refuses a second decision, so
		# this just clears a phantom actionable row rather than fixing integrity.
		_broadcast_task_decision(doc)

	state = doc.get("workflow_state") or doc.get("status") or doc.get("approval_status")
	return {"name": doc.name, "doctype": doctype, "state": state}


@frappe.whitelist()
def reject_request(doctype: str, name: str, comment: str | None = None) -> dict:
	"""Reject one inbox item. A comment is REQUIRED (rejections need a reason).
	Enforces approver authorization server-side."""
	if not comment or not strip_html(comment).strip():
		frappe.throw(_("A comment is required when rejecting a request."))

	if doctype not in _APPROVAL_DOCTYPES:
		frappe.throw(_("Unsupported approval document type: {0}").format(doctype))

	doc = frappe.get_doc(doctype, name)
	_validate_approver(doc)
	# Capture the requester's User up front — some branches delete the doc.
	requester_user = _requester_user(doctype, doc)

	if doctype == "Leave Application":
		doc.status = "Rejected"
		doc.save(ignore_permissions=True)
		if doc.docstatus == 0:
			doc.submit()
	elif doctype == "Expense Claim":
		doc.approval_status = "Rejected"
		doc.save(ignore_permissions=True)
		if doc.docstatus == 0:
			doc.submit()
	elif doctype == "Shift Request":
		doc.status = "Rejected"
		doc.save(ignore_permissions=True)
		if doc.docstatus == 0:
			doc.submit()
	elif doctype == "Attendance Request":
		# Persist the rejection (do NOT delete) so the employee sees it, with the
		# reason. Terminal state — they raise a fresh request if needed.
		if doc.docstatus != 0:
			frappe.throw(
				_("Only a pending Attendance Request can be rejected. Cancel the approved request instead.")
			)
		if frappe.get_meta(doctype).has_field("status"):
			# db_set (not save) so a rejection is NEVER blocked by the request's
			# own validate() — e.g. the requested days later became On Leave, the
			# shift changed, or the employee went inactive. Killing a request must
			# not depend on whether it could still be enacted.
			doc.db_set({"status": "Rejected", "rejection_reason": strip_html(comment).strip()})
		else:
			# Field not present (older site mid-migrate) — fall back to old behaviour.
			doc.delete(ignore_permissions=True)
	elif doctype == "Employee Advance":
		# No reject status — cancel the draft request.
		if doc.docstatus == 0:
			doc.delete(ignore_permissions=True)
	elif doctype == "Goal":
		# Bounce the completion back to the employee to redo.
		#
		# Only a submitted, still-undecided instance can be sent back — the same
		# gate approve uses. Without it a second approver (role-routed approval and
		# the HR backstop both put one instance in several inboxes) could reject an
		# instance the FIRST approver already accepted, silently erasing that
		# sign-off and un-completing accepted work; and a never-submitted instance
		# could be "rejected", planting a phantom "sent back" note on the employee.
		awaiting = doc.status == "In Progress" and (
			not doc.meta.has_field("submitted_at") or doc.get("submitted_at")
		)
		if not awaiting:
			frappe.throw(_("This task is not awaiting approval."))
		# progress=0 means Goal.set_status() derives 'Pending' during validate —
		# so we set Pending explicitly rather than pretending it stays 'In
		# Progress' (the previous code claimed that and was silently overridden).
		# Pending is also correct semantically: it is open work again.
		#
		# The reason is persisted to approval_notes, not just the timeline, so the
		# employee actually SEES why it came back (mirrors Attendance Request's
		# rejection_reason). Submission + approval stamps are cleared so the next
		# attempt is a clean cycle.
		doc.status = "Pending"
		doc.progress = 0
		for field, value in (
			("submitted_at", None),
			("submitted_by", None),
			("approved_by", None),
			("approved_at", None),
			("approval_notes", strip_html(comment).strip() if comment else None),
		):
			if doc.meta.has_field(field):
				doc.set(field, value)
		doc.flags.ihc_governed_write = True
		doc.save(ignore_permissions=True)
	elif doctype == "Resignation Request":
		from frappe.model.workflow import apply_workflow, get_transitions

		actions = {t.get("action") for t in get_transitions(doc)}
		if "Reject" in actions:
			apply_workflow(doc, "Reject")
		elif "Withdraw" in actions:
			apply_workflow(doc, "Withdraw")
		else:
			frappe.throw(
				_("No rejection transition is available for this resignation request.")
			)
	elif doctype == "Employee Profile Change Request":
		from indian_hrms_compliance.hr.doctype.employee_profile_change_request.employee_profile_change_request import (
			reject_profile_change_request,
		)

		reject_profile_change_request(name, comment=comment)
		doc = frappe.get_doc(doctype, name)
	elif doctype == "Employee Onboarding Application":
		doc.status = "Rejected"
		doc.rejection_reason = comment
		doc.save(ignore_permissions=True)
	elif doctype == "Employee Grievance":
		# Reject = mark Invalid; the comment becomes cause_of_grievance (the
		# grievance form requires that field when status is Investigated/Resolved/Invalid).
		doc.status = "Invalid"
		if not doc.cause_of_grievance:
			doc.cause_of_grievance = comment
		doc.save(ignore_permissions=True)

	# Goal still exists after reject; for deleted docs add_comment would fail.
	if frappe.db.exists(doctype, name):
		doc = frappe.get_doc(doctype, name)
		_add_comment_if_any(doc, comment)
	# Notify the requester their item was rejected (requester_user was captured
	# before any branch could delete the doc). Skips the self-notifying doctypes.
	_notify_requester_decision(doctype, name, requester_user, approved=False, comment=comment)
	frappe.db.commit()

	# Live-refresh: rejecter's inbox + requester's screens. For deleted docs
	# (Advance/Attendance Request) we already captured employee.user_id above
	# in the variable that still exists.
	_pwa_refetch(list(_INBOX_CACHE_KEYS), user=frappe.session.user)
	emp_field = (doc.get("employee") if frappe.db.exists(doctype, name) else None) or None
	if emp_field:
		req_user = frappe.db.get_value("Employee", emp_field, "user_id")
		_refresh_requester(doctype, req_user)
	if doctype == "Goal":
		# Drop the now-decided instance from every other reviewer's cached inbox.
		_broadcast_task_decision(doc)

	return {"name": name, "doctype": doctype, "rejected": True}


@frappe.whitelist()
def request_attendance_clarification(name: str, comment: str | None = None) -> dict:
	"""Send an Attendance Request back to the employee for clarification instead
	of approving or rejecting. Requires a comment; approver-authorized."""
	if not comment or not strip_html(comment).strip():
		frappe.throw(_("A comment is required when asking for clarification."))

	doc = frappe.get_doc("Attendance Request", name)
	_validate_approver(doc)

	if not frappe.get_meta("Attendance Request").has_field("status"):
		frappe.throw(_("The clarification workflow is not available on this site yet."))
	if doc.docstatus != 0:
		frappe.throw(_("Only a pending request can be sent back for clarification."))

	# db_set (not save) so sending back for clarification is never blocked by the
	# request's own validate() (see reject_request for the rationale).
	reason = strip_html(comment).strip()
	doc.db_set({"status": "Needs Clarification", "rejection_reason": reason})
	_add_comment_if_any(doc, comment)

	# Notify the employee: unlike Leave/Expense (whose save-time hooks fire
	# notify_approval_status), an Attendance Request is moved via db_set, so we
	# raise the PWA Notification here explicitly.
	req_user = frappe.db.get_value("Employee", doc.employee, "user_id")
	_notify_attendance_clarification(doc, req_user, reason)
	frappe.db.commit()

	_pwa_refetch(list(_INBOX_CACHE_KEYS), user=frappe.session.user)
	_refresh_requester("Attendance Request", req_user)
	return {"name": name, "doctype": "Attendance Request", "status": "Needs Clarification"}


def _notify_attendance_clarification(doc, req_user: str | None, reason: str) -> None:
	"""Raise a PWA Notification telling the employee their Attendance Request was
	sent back for clarification, with the approver's question."""
	from_user = frappe.session.user
	if not req_user or req_user == from_user:
		return

	from frappe import bold

	from_name = frappe.db.get_value("User", from_user, "full_name", cache=True) or from_user
	notification = frappe.new_doc("PWA Notification")
	notification.from_user = from_user
	notification.to_user = req_user
	notification.message = (
		f"{bold(from_name)} asked for clarification on your {bold('Attendance Request')} "
		f"{doc.name}: {reason}"
	)
	notification.reference_document_type = "Attendance Request"
	notification.reference_document_name = doc.name
	notification.insert(ignore_permissions=True)


@frappe.whitelist()
def resubmit_attendance_request(name: str) -> dict:
	"""Employee re-submits a request that was sent back for clarification.
	Moves it Needs Clarification → Open so it re-enters the manager's queue."""
	doc = frappe.get_doc("Attendance Request", name)

	if not frappe.get_meta("Attendance Request").has_field("status"):
		frappe.throw(_("The clarification workflow is not available on this site yet."))

	# Only the requesting employee (or an HR user) may resubmit.
	emp_user = frappe.db.get_value("Employee", doc.employee, "user_id")
	if frappe.session.user != emp_user and not _is_hr_user(frappe.session.user):
		frappe.throw(_("You are not allowed to resubmit this request."), frappe.PermissionError)

	if doc.docstatus != 0:
		frappe.throw(_("This request can no longer be resubmitted."))
	if doc.status != "Needs Clarification":
		frappe.throw(_("Only a request awaiting clarification can be resubmitted."))

	doc.status = "Open"
	doc.rejection_reason = None
	doc.save(ignore_permissions=True)

	# Notify the manager it's back in their queue (before commit so it's atomic).
	reports_to = frappe.db.get_value("Employee", doc.employee, "reports_to")
	manager_user = frappe.db.get_value("Employee", reports_to, "user_id") if reports_to else None
	if manager_user and manager_user != frappe.session.user:
		from frappe import bold

		emp_name = doc.get("employee_name") or doc.employee
		try:
			frappe.get_doc(
				{
					"doctype": "PWA Notification",
					"from_user": frappe.session.user,
					"to_user": manager_user,
					"message": (
						f"{bold(emp_name)} responded to your clarification and re-submitted "
						f"{bold('Attendance Request')} {doc.name}"
					),
					"reference_document_type": "Attendance Request",
					"reference_document_name": doc.name,
				}
			).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(f"PWA resubmit notification failed: {doc.name}")

	frappe.db.commit()

	# Live-refresh the employee's own list AND the approving manager's inbox.
	_refresh_requester("Attendance Request", emp_user)
	if manager_user:
		_pwa_refetch(list(_INBOX_CACHE_KEYS), user=manager_user)
	return {"name": name, "status": "Open"}
