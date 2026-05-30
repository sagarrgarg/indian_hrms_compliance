# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""ESI Half Yearly Aggregator — Phase 6B-1.

Pulls the up-to-six ESI Monthly Contribution docs that fall in the
target period (Apr-Sep / Oct-Mar) for a given (Company × Fiscal Year),
links them into the ESI Half Yearly Return.linked_monthly_filings
table, sums totals, and renders a clean summary HTML block.

This is intentionally a one-button aggregator — HR can re-click to
refresh if a monthly filing is added / corrected post-creation.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate


PERIOD_MONTHS = {
	"Apr-Sep": [4, 5, 6, 7, 8, 9],
	"Oct-Mar": [10, 11, 12, 1, 2, 3],
}


def _period_bounds(fiscal_year, period):
	"""Return (start_date, end_date) for the period under a given FY.

	For Apr-Sep the calendar year = fy_start.year.
	For Oct-Mar the months span fy_start.year and fy_end.year (Oct, Nov,
	Dec are in fy_start.year; Jan, Feb, Mar are in fy_end.year).
	"""
	fy = frappe.db.get_value(
		"Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not fy:
		frappe.throw(_("Fiscal Year {0} not found.").format(fiscal_year))
	fy_start = getdate(fy.year_start_date)
	fy_end = getdate(fy.year_end_date)
	if period == "Apr-Sep":
		return date(fy_start.year, 4, 1), date(fy_start.year, 9, 30)
	# Oct-Mar
	return date(fy_start.year, 10, 1), date(fy_end.year, 3, 31)


@frappe.whitelist()
def aggregate_esi_half_yearly(esi_hy_name):
	"""Refresh linked monthly filings + totals + summary HTML for an
	ESI Half Yearly Return doc."""
	doc = frappe.get_doc("ESI Half Yearly Return", esi_hy_name)
	if doc.filing_status == "Filed":
		frappe.throw(
			_(
				"ESI Half Yearly Return {0} is Filed — un-file it (set status back to Draft) before re-aggregating."
			).format(doc.name)
		)

	period_start, period_end = _period_bounds(doc.fiscal_year, doc.period)

	# Find all monthly filings for the company in this period (not cancelled).
	monthly = frappe.get_all(
		"ESI Monthly Contribution",
		filters={
			"company": doc.company,
			"wage_month": (">=", period_start),
			"wage_month": ("<=", period_end),
			"filing_status": ("!=", "Cancelled"),
		},
		fields=[
			"name",
			"wage_month",
			"wage_month_label",
			"total_wages",
			"total_contribution",
			"filing_status",
			"total_ips",
		],
		order_by="wage_month",
	)
	# Belt-and-braces — the filter dict with duplicate wage_month keys can
	# be overwritten in older Frappe versions. Re-filter in Python.
	monthly = [m for m in monthly if period_start <= getdate(m.wage_month) <= period_end]

	# Reset and rebuild the linked table.
	doc.set("linked_monthly_filings", [])
	total_wages = 0
	total_contribution = 0
	for m in monthly:
		doc.append(
			"linked_monthly_filings",
			{
				"monthly_filing": m.name,
				"wage_month_label": m.wage_month_label,
				"total_wages": m.total_wages,
				"total_contribution": m.total_contribution,
			},
		)
		total_wages += flt(m.total_wages)
		total_contribution += flt(m.total_contribution)

	doc.total_wages_period = total_wages
	doc.total_contribution_period = total_contribution
	doc.summary_html = _build_summary_html(doc, monthly, period_start, period_end)

	doc.save(ignore_permissions=True)
	return {
		"name": doc.name,
		"months_linked": len(monthly),
		"total_wages_period": total_wages,
		"total_contribution_period": total_contribution,
	}


def _build_summary_html(doc, monthly, period_start, period_end):
	"""Render a compact HTML summary table of the linked monthly filings."""
	if not monthly:
		return (
			f"<p><em>No ESI Monthly Contribution docs found for "
			f"{doc.company} in {doc.period} ({formatdate(period_start)} – "
			f"{formatdate(period_end)}).</em></p>"
		)
	rows_html = "".join(
		f"<tr>"
		f"<td>{m.wage_month_label or formatdate(m.wage_month)}</td>"
		f"<td>{m.name}</td>"
		f"<td>{int(m.total_ips or 0)}</td>"
		f"<td style='text-align:right'>{flt(m.total_wages):,.2f}</td>"
		f"<td style='text-align:right'>{flt(m.total_contribution):,.2f}</td>"
		f"<td>{m.filing_status}</td>"
		f"</tr>"
		for m in monthly
	)
	total_wages = sum(flt(m.total_wages) for m in monthly)
	total_contribution = sum(flt(m.total_contribution) for m in monthly)
	total_ips = sum(int(m.total_ips or 0) for m in monthly)
	return (
		f"<h4>ESI Half Yearly Return — {doc.company} / {doc.fiscal_year} / {doc.period}</h4>"
		f"<p>Period: <strong>{formatdate(period_start)}</strong> to "
		f"<strong>{formatdate(period_end)}</strong>. "
		f"Months linked: <strong>{len(monthly)}</strong> of 6 expected.</p>"
		f"<table class='table table-bordered' style='width:100%;font-size:13px'>"
		f"<thead><tr>"
		f"<th>Wage Month</th><th>Monthly Filing</th><th>IPs</th>"
		f"<th style='text-align:right'>Total Wages</th>"
		f"<th style='text-align:right'>Total Contribution</th>"
		f"<th>Status</th>"
		f"</tr></thead><tbody>{rows_html}</tbody>"
		f"<tfoot><tr style='font-weight:bold;background:#f7f7f7'>"
		f"<td colspan='2'>Total</td>"
		f"<td>{total_ips}</td>"
		f"<td style='text-align:right'>{total_wages:,.2f}</td>"
		f"<td style='text-align:right'>{total_contribution:,.2f}</td>"
		f"<td></td>"
		f"</tr></tfoot>"
		f"</table>"
	)
