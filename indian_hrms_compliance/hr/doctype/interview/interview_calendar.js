frappe.views.calendar["Interview"] = {
	field_map: {
		start: "from",
		end: "to",
		id: "name",
		title: "subject",
		allDay: "allDay",
		color: "color",
	},
	order_by: "scheduled_on",
	gantt: true,
	get_events_method: "indian_hrms_compliance.hr.doctype.interview.interview.get_events",
};
