# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""OSH Annual Return Form 26 generator.

Whitelisted endpoint called from the form-side `Generate` button:

  frappe.call({
      method: "indian_hrms_compliance.overrides.osh_form_26_generator.generate_osh_form_26",
      args: { form_name: cur_frm.doc.name }
  })

Validates the workforce numbers, pulls average daily workers from Attendance
when available, generates a basic HTML/PDF summary, and stamps the doc as
Generated.
"""

from io import BytesIO

import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.utils.file_manager import save_file
from frappe.utils.pdf import get_pdf


def _hr_setting(field, default=None):
	meta = frappe.get_meta("HR Settings")
	if not meta.get_field(field):
		return default
	val = frappe.db.get_single_value("HR Settings", field)
	return default if val in (None, "") else val


def _compute_avg_daily_workers(company, fy_name):
	"""Average daily worker count from Attendance (Present + Half Day) for
	the fiscal year. Returns 0 when Attendance data is unavailable."""
	fy = frappe.db.get_value(
		"Fiscal Year", fy_name, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not fy:
		return 0
	try:
		rows = frappe.db.sql(
			"""
			SELECT attendance_date, COUNT(*) AS cnt
			FROM `tabAttendance`
			WHERE company = %s
			  AND attendance_date BETWEEN %s AND %s
			  AND status IN ('Present', 'Half Day', 'Work From Home')
			  AND docstatus = 1
			GROUP BY attendance_date
			""",
			(company, fy.year_start_date, fy.year_end_date),
			as_dict=True,
		)
	except Exception:
		# Attendance table may not exist in stripped-down sites
		return 0
	if not rows:
		return 0
	return int(round(sum(r.cnt for r in rows) / len(rows)))


def _build_summary_html(doc):
	"""Produce a basic Form 26 summary HTML for the attached PDF."""
	rows = [
		("Company", doc.company),
		("Fiscal Year", doc.fiscal_year),
		("Establishment Type", doc.establishment_type or ""),
		("Establishment Registration No.", doc.establishment_registration_number or ""),
		("Total Workers (Male)", doc.total_workers_male or 0),
		("Total Workers (Female)", doc.total_workers_female or 0),
		("Total Workers (Others)", doc.total_workers_others or 0),
		("Total Workers", doc.total_workers or 0),
		("Contract Workers", doc.contract_workers_count or 0),
		("Average Daily Workers", doc.average_daily_workers or 0),
		("Average Monthly Overtime Hours", doc.average_monthly_overtime_hours or 0),
		("Safety Committee Constituted", "Yes" if doc.safety_committee_constituted else "No"),
		("Safety Committee Size", doc.safety_committee_size or 0),
		("Safety Meetings Held", doc.safety_meetings_held or 0),
		("Fatal Accidents", doc.fatal_accidents or 0),
		("Non-Fatal (Lost-Time)", doc.non_fatal_accidents_lost_time or 0),
		("Non-Fatal (Minor)", doc.non_fatal_accidents_minor or 0),
		("Total Man-Days Lost", doc.total_man_days_lost_to_accidents or 0),
		("Compensation Paid", doc.compensation_paid or 0),
		("Safety Trainings Conducted", doc.safety_trainings_conducted or 0),
		("Workers Trained", doc.workers_trained or 0),
		("Medical Examinations Conducted", doc.medical_examinations_conducted or 0),
	]
	body = "".join(
		f"<tr><td style='padding:4px 8px;border:1px solid #ddd'>{k}</td>"
		f"<td style='padding:4px 8px;border:1px solid #ddd'>{v}</td></tr>"
		for k, v in rows
	)
	return (
		"<html><body style='font-family:Arial,sans-serif'>"
		f"<h2>Form 26 — OSH&amp;WC Code Annual Return</h2>"
		f"<p><b>Document:</b> {doc.name}</p>"
		f"<table style='border-collapse:collapse;width:100%'>{body}</table>"
		"</body></html>"
	)


@frappe.whitelist()
def generate_osh_form_26(form_name):
	"""Generate the Form 26 summary PDF and stamp the doc as Generated."""
	doc = frappe.get_doc("OSH Annual Return Form 26", form_name)
	if doc.filing_status == "Filed":
		frappe.throw(_("Cannot regenerate — this return has already been Filed."))

	exceptions = []

	# Recompute totals
	doc.total_workers = (
		(doc.total_workers_male or 0)
		+ (doc.total_workers_female or 0)
		+ (doc.total_workers_others or 0)
	)

	# Fallback: pull avg daily workers from Attendance if not manually set
	if not doc.average_daily_workers:
		avg = _compute_avg_daily_workers(doc.company, doc.fiscal_year)
		if avg:
			doc.average_daily_workers = avg
		else:
			exceptions.append(
				"Average Daily Workers fallback from Attendance returned 0. Enter manually."
			)

	# Safety Committee mandatory when total_workers > Sec 96 threshold
	threshold = int(_hr_setting("safety_committee_threshold_workers", 250) or 250)
	if (doc.total_workers or 0) > threshold and not doc.safety_committee_constituted:
		exceptions.append(
			f"Total workers ({doc.total_workers}) exceeds Sec 96 threshold ({threshold}) "
			"but Safety Committee Constituted is off."
		)

	# Generate PDF
	try:
		html = _build_summary_html(doc)
		pdf_bytes = get_pdf(html)
		buf = BytesIO(pdf_bytes)
		fname = f"OSH26_{doc.name}.pdf"
		file_doc = save_file(
			fname,
			buf.getvalue(),
			"OSH Annual Return Form 26",
			doc.name,
			is_private=1,
		)
		doc.attached_pdf = file_doc.file_url
	except Exception as e:
		exceptions.append(f"PDF generation failed: {e}")
		frappe.log_error(frappe.get_traceback(), "OSH Form 26 PDF Generation Failed")

	doc.generated_on = now_datetime()
	doc.filing_status = "Generated"
	doc.exceptions = "\n".join(exceptions) if exceptions else ""
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"name": doc.name,
		"total_workers": doc.total_workers,
		"average_daily_workers": doc.average_daily_workers,
		"filing_status": doc.filing_status,
		"exceptions": exceptions,
		"attached_pdf": doc.attached_pdf,
	}
