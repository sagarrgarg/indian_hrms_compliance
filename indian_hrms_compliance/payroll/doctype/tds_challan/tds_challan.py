# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""TDS Challan (ITNS 281) — the bank challan for depositing salary TDS (sec 192).

generate_tds_challan(company, fiscal_year, quarter) rolls up the TDS actually
deducted across submitted Salary Slips in the quarter into a single draft
challan. HR fills BSR/CIN/date after paying and marks it Deposited; the voucher
prints from the ITNS 281 format.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class TDSChallan(Document):
	def validate(self):
		self.total_amount = (
			flt(self.tds_amount) + flt(self.surcharge) + flt(self.education_cess)
			+ flt(self.interest) + flt(self.fee_234e) + flt(self.penalty) + flt(self.others)
		)


def _quarter_tds(company, period_start, period_end):
	"""Sum the TDS deducted across submitted slips in the period, using the
	company's Statutory Component Mapping (income_tax_component) with an
	'Income Tax'/'TDS' substring fallback."""
	from indian_hrms_compliance.hr.doctype.statutory_component_mapping.statutory_component_mapping import (
		get_mapping_for_company,
	)

	mapping = get_mapping_for_company(company)
	comp = mapping.income_tax_component if mapping else None

	from frappe.query_builder.functions import Sum

	ss = frappe.qb.DocType("Salary Slip")
	sd = frappe.qb.DocType("Salary Detail")
	q = (
		frappe.qb.from_(ss).join(sd).on(sd.parent == ss.name)
		.select(Sum(sd.amount))
		.where(ss.docstatus == 1)
		.where(ss.company == company)
		.where(sd.parentfield == "deductions")
		.where(ss.start_date >= period_start)
		.where(ss.start_date <= period_end)
	)
	if comp:
		q = q.where(sd.salary_component == comp)
	else:
		q = q.where((sd.salary_component.like("%Income Tax%")) | (sd.salary_component.like("%TDS%")))
	res = q.run()
	return flt(res[0][0]) if res and res[0][0] else 0.0


@frappe.whitelist()
def generate_tds_challan(company, fiscal_year, quarter):
	frappe.only_for(("HR Manager", "HR User", "System Manager"))
	from indian_hrms_compliance.payroll.doctype.tds_return_form_24q.tds_return_form_24q import get_quarter_dates

	period_start, period_end = get_quarter_dates(fiscal_year, quarter)
	tds = _quarter_tds(company, period_start, period_end)

	existing = frappe.db.exists(
		"TDS Challan", {"company": company, "fiscal_year": fiscal_year, "quarter": quarter, "status": "Draft"}
	)
	doc = frappe.get_doc("TDS Challan", existing) if existing else frappe.new_doc("TDS Challan")
	tan = frappe.db.get_value("Company", company, "tax_id")
	pan = frappe.db.get_value("Company", company, "pan")
	# Assessment Year = FY + 1 (FY 2025-2026 -> AY 2026-2027).
	ay = None
	try:
		start_y = int(str(fiscal_year)[:4])
		ay = f"{start_y + 1}-{start_y + 2}"
	except Exception:
		ay = fiscal_year

	doc.update({
		"company": company, "fiscal_year": fiscal_year, "quarter": quarter,
		"section_code": "192", "tan": tan, "pan": pan, "assessment_year": ay,
		"period_from": period_start, "period_to": period_end,
		"tds_amount": tds,
	})
	doc.flags.ignore_permissions = True
	doc.save()
	return {"name": doc.name, "tds_amount": tds, "total_amount": doc.total_amount}
