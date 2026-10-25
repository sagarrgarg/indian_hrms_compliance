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
