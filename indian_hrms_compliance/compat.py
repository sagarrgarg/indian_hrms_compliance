"""Differences between Frappe/ERPNext v15 and v16 that this app has to bridge.

The app ships from one branch for both versions. Any call whose signature or
behaviour differs between them goes through a helper here, so the version
check lives in one place instead of being repeated across the code.
"""

import inspect

import frappe

FRAPPE_MAJOR = int(frappe.__version__.split(".")[0])
IS_V16 = FRAPPE_MAJOR >= 16


def rebuild_tree(doctype: str, parent_field: str) -> None:
	"""Rebuild a NestedSet tree.

	v15 takes the parent field as an argument; v16 reads it from the DocType's
	nsm_parent_field and accepts the doctype only."""
	from frappe.utils.nestedset import rebuild_tree as _rebuild_tree

	if len(inspect.signature(_rebuild_tree).parameters) > 1:
		_rebuild_tree(doctype, parent_field)
	else:
		_rebuild_tree(doctype)


def agg(func: str, field: str, alias: str):
	"""One aggregate column for the `fields` of frappe.get_all / get_list.

	v16 rejects SQL functions written as strings ("SUM(x) as y") and takes
	{"SUM": "x", "as": "y"} instead; v15 only understands the string form."""
	func = func.upper()
	if IS_V16:
		return {func: field, "as": alias}
	return f"{func}({field}) as {alias}"


def literal(value: str, alias: str):
	"""A constant column, e.g. 'Attendance' as doctype, for get_all / get_list `fields`."""
	if IS_V16:
		from frappe.query_builder import ValueWrapper

		return ValueWrapper(value).as_(alias)
	return f"'{value}' as {alias}"


def neutralise_half_day_holidays(doc, method=None):
	"""Holiday List validate hook: keep every holiday a full day on v16.

	ERPNext v16 added Holiday(.List).is_half_day. Its holiday_list.is_holiday() skips half-day
	rows while employee.is_holiday() and this app's payroll and leave code count them as full
	holidays, so attendance and payroll would disagree about the same day. v15 has no half-day
	holidays; this keeps that meaning."""
	if not IS_V16:
		return
	doc.is_half_day = 0
	for row in doc.get("holidays") or []:
		row.is_half_day = 0
	doc.total_holidays = len(doc.get("holidays") or [])


def hide_half_day_holidays():
	"""after_migrate / after_install: hide v16's half-day holiday checkboxes and clear any
	rows ticked before this fix (see neutralise_half_day_holidays)."""
	if not IS_V16 or not frappe.get_meta("Holiday").has_field("is_half_day"):
		return
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype in ("Holiday List", "Holiday"):
		make_property_setter(doctype, "is_half_day", "hidden", 1, "Check", validate_fields_for_doctype=False)

	for holiday_list in frappe.get_all("Holiday", filters={"is_half_day": 1}, pluck="parent", distinct=True):
		frappe.db.set_value("Holiday", {"parent": holiday_list, "is_half_day": 1}, "is_half_day", 0)
		frappe.db.set_value(
			"Holiday List",
			holiday_list,
			"total_holidays",
			frappe.db.count("Holiday", {"parent": holiday_list}),
			update_modified=False,
		)
	frappe.db.set_value("Holiday List", {"is_half_day": 1}, "is_half_day", 0, update_modified=False)


def prune_missing_workspace_links():
	"""after_migrate / after_install: drop workspace links to DocTypes this Frappe lacks.

	v16 removed Energy Points, and on v16 a single link to a missing DocType makes
	Workspace.get_links return no cards at all, so the Performance workspace showed none.
	No-op on v15, where every link target exists."""
	workspaces = frappe.get_all("Workspace", filters={"module": ("in", ["HR", "Payroll"])}, pluck="name")
	if not workspaces:
		return
	for link in frappe.get_all(
		"Workspace Link",
		filters={"parenttype": "Workspace", "parent": ("in", workspaces), "type": "Link", "link_type": "DocType"},
		fields=["name", "link_to"],
	):
		if link.link_to and not frappe.db.exists("DocType", link.link_to):
			# a direct delete, not doc.save(), so developer mode doesn't re-export the JSON
			frappe.db.delete("Workspace Link", {"name": link.name})


# v15 Frappe's money_in_words, used on v16 so amounts in words keep v15's wording.
# v16 takes the number format from the user's Language or System Settings rather than the
# Currency, so INR could read "One Hundred And Twenty Thousand" instead of "One Lakh, Twenty
# Thousand", and it derives decimals from fraction_units.
_V15_FORMAT_DECIMALS = {
	"#,###.##": 2, "#.###,##": 2, "# ###.##": 2, "# ###,##": 2, "#'###.##": 2, "#, ###.##": 2,
	"#,##,###.##": 2, "#,###.###": 3, "#.###": 0, "#,###": 0, "#.########": 8,
}


def money_in_words(number, main_currency=None, fraction_currency=None):
	from frappe.utils import money_in_words as frappe_money_in_words

	if not IS_V16:
		return frappe_money_in_words(number, main_currency, fraction_currency)

	from frappe.utils import cint, flt, get_defaults, in_words

	_ = frappe._
	try:
		number = float(number)
	except ValueError:
		return ""
	number = flt(number)
	if number < 0:
		return ""
	if not main_currency:
		main_currency = get_defaults().get("currency", "INR")
	if not fraction_currency:
		fraction_currency = frappe.db.get_value("Currency", main_currency, "fraction", cache=True) or _("Cent")
	number_format = (
		frappe.db.get_value("Currency", main_currency, "number_format", cache=True)
		or frappe.db.get_default("number_format")
		or "#,###.##"
	)
	fraction_length = _V15_FORMAT_DECIMALS.get(number_format, 2)
	n = f"%.{fraction_length}f" % number
	numbers = n.split(".")
	main, fraction = numbers if len(numbers) > 1 else [n, "00"]
	if len(fraction) < fraction_length:
		fraction += "0" * (fraction_length - len(fraction))
	in_million = number_format != "#,##,###.##"

	if main == "0" and fraction in ["00", "000"]:
		out = _(main_currency, context="Currency") + " " + _("Zero")
	elif main == "0":
		out = in_words(fraction, in_million).title() + " " + _(fraction_currency, context="Currency")
	else:
		if main_currency == "DZD":
			out = in_words(main, in_million).title() + " " + _("Dinars", context="Currency")
		else:
			out = _(main_currency, context="Currency") + " " + in_words(main, in_million).title()
		if cint(fraction):
			out = (
				out + " " + _("and") + " " + in_words(fraction, in_million).title() + " "
				+ _(fraction_currency, context="Currency")
			)
	if main_currency == "DZD":
		return out + "."
	return out + " " + _("only.")


def commit_is_ignored() -> bool:
	"""True inside v16 doc_events handlers, where frappe.db.commit() and rollback() do nothing."""
	return bool(getattr(frappe.local.db, "_disable_transaction_control", 0))
