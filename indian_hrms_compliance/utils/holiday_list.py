import frappe
from frappe.utils import getdate


def get_holiday_dates_between(
	holiday_list: str,
	start_date: str,
	end_date: str,
	skip_weekly_offs: bool = False,
) -> list:
	Holiday = frappe.qb.DocType("Holiday")
	query = (
		frappe.qb.from_(Holiday)
		.select(Holiday.holiday_date)
		.where((Holiday.parent == holiday_list) & (Holiday.holiday_date.between(start_date, end_date)))
		.orderby(Holiday.holiday_date)
	)

	if skip_weekly_offs:
		query = query.where(Holiday.weekly_off == 0)

	return query.run(pluck=True)


def get_holiday_weekly_off_map(holiday_list: str, start_date: str, end_date: str) -> dict:
	"""{holiday_date: is_weekly_off} for the range — lets callers tell a weekly off
	(Sunday) apart from a festival/national holiday, which the sandwich rule needs."""
	Holiday = frappe.qb.DocType("Holiday")
	rows = (
		frappe.qb.from_(Holiday)
		.select(Holiday.holiday_date, Holiday.weekly_off)
		.where((Holiday.parent == holiday_list) & (Holiday.holiday_date.between(start_date, end_date)))
		.run(as_dict=True)
	)
	return {getdate(row.holiday_date): int(row.weekly_off or 0) for row in rows}


def invalidate_cache(doc, method=None):
	from indian_hrms_compliance.payroll.doctype.salary_slip.salary_slip import HOLIDAYS_BETWEEN_DATES

	frappe.cache().delete_value(HOLIDAYS_BETWEEN_DATES)
