import { createResource } from "frappe-ui"

export const pendingApprovals = createResource({
	url: "indian_hrms_compliance.api.get_pending_approvals",
	auto: true,
	cache: "indian_hrms_compliance:pending_approvals",
})

export const approvalsSummary = createResource({
	url: "indian_hrms_compliance.api.get_approvals_summary",
	auto: true,
	cache: "indian_hrms_compliance:approvals_summary",
})

export const approveRequest = createResource({
	url: "indian_hrms_compliance.api.approve_request",
})

export const rejectRequest = createResource({
	url: "indian_hrms_compliance.api.reject_request",
})

// Attendance Request only — bounce the request back to the employee for
// clarification instead of an outright approve/reject.
export const requestClarification = createResource({
	url: "indian_hrms_compliance.api.request_attendance_clarification",
})
