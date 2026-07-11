# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, get_first_day, get_last_day, getdate

import erpnext

from indian_hrms_compliance.hr.utils import calculate_tax_with_marginal_relief


class IncomeTaxSlab(Document):
	def validate(self):
		if self.company:
			self.currency = erpnext.get_company_currency(self.company)


def calculate_tax_by_tax_slab(annual_taxable_earning, tax_slab, eval_globals=None, eval_locals=None):
	eval_globals = eval_globals or {}
	eval_locals = eval_locals or {}

	if annual_taxable_earning <= tax_slab.tax_relief_limit:
		return 0, 0

	tax_amount = calculate_base_tax_from_tax_slabs(
		annual_taxable_earning, tax_slab, eval_globals, eval_locals
	)

	if tax_with_marginal_relief := calculate_tax_with_marginal_relief(
		tax_slab, tax_amount, annual_taxable_earning
	):
		tax_amount = tax_with_marginal_relief

	tax_amount, surcharge = apply_surcharge_with_marginal_relief(
		tax_amount, annual_taxable_earning, tax_slab, eval_globals, eval_locals
	)

	tax_amount, other_taxes = calculate_other_charges(tax_amount, annual_taxable_earning, tax_slab)
	return tax_amount, surcharge + other_taxes


def calculate_base_tax_from_tax_slabs(annual_taxable_earning, tax_slab, eval_globals, eval_locals):
	tax_amount = 0
	eval_locals.update({"annual_taxable_earning": annual_taxable_earning})

	for slab in tax_slab.slabs:
		cond = cstr(slab.condition).strip()
		if cond and not eval_tax_slab_condition(cond, eval_globals, eval_locals):
			continue
		if not slab.to_amount and annual_taxable_earning >= slab.from_amount:
			tax_amount += (annual_taxable_earning - slab.from_amount + 1) * slab.percent_deduction * 0.01
			continue
		if annual_taxable_earning >= slab.from_amount and annual_taxable_earning < slab.to_amount:
			tax_amount += (annual_taxable_earning - slab.from_amount + 1) * slab.percent_deduction * 0.01
		elif annual_taxable_earning >= slab.from_amount and annual_taxable_earning >= slab.to_amount:
			tax_amount += (slab.to_amount - slab.from_amount + 1) * slab.percent_deduction * 0.01
	return tax_amount


def calculate_other_charges(tax_amount, annual_taxable_earning, tax_slab):
	total_other_taxes_and_charges = 0
	for d in tax_slab.other_taxes_and_charges:
		if flt(d.min_taxable_income) and flt(d.min_taxable_income) > annual_taxable_earning:
			continue

		if flt(d.max_taxable_income) and flt(d.max_taxable_income) < annual_taxable_earning:
			continue
		other_taxes_and_charges = tax_amount * flt(d.percent) / 100
		tax_amount += other_taxes_and_charges
		total_other_taxes_and_charges += other_taxes_and_charges

	return tax_amount, total_other_taxes_and_charges


def eval_tax_slab_condition(condition, eval_globals=None, eval_locals=None):
	if not eval_globals:
		eval_globals = {
			"int": int,
			"float": float,
			"long": int,
			"round": round,
			"date": date,
			"getdate": getdate,
			"get_first_day": get_first_day,
			"get_last_day": get_last_day,
		}
	try:
		condition = condition.strip()
		if condition:
			return frappe.safe_eval(condition, eval_globals, eval_locals)
	except NameError as err:
		frappe.throw(
			_("{0} <br> This error can be due to missing or deleted field.").format(str(err)),
			title=_("Name error"),
		)
	except SyntaxError as err:
		frappe.throw(_("Syntax error in condition: {0} in Income Tax Slab").format(str(err)))
	except Exception as e:
		frappe.throw(_("Error in formula or condition: {0} in Income Tax Slab").format(str(e)))
		raise


@erpnext.allow_regional
def apply_surcharge_with_marginal_relief(
	tax_amount, annual_taxable_earning, tax_slab, eval_globals, eval_locals
):
	"""Surcharge on income tax (high earners). New regime caps at 25%.

	indian_hrms_compliance (sagarrgarg a80b3b266) implements the statutory Indian
	surcharge here — v16's hook point for it (upstream returns 0). Runs after the
	87A marginal relief and before cess, so cess is levied on tax + surcharge."""
	if annual_taxable_earning <= tax_slab.tax_relief_limit:
		return tax_amount, 0

	def _slab_tax(income):
		t = 0
		for slab in tax_slab.slabs:
			cond = cstr(slab.condition).strip()
			if cond and not eval_tax_slab_condition(cond, eval_globals, eval_locals):
				continue
			if not slab.to_amount and income >= slab.from_amount:
				t += (income - slab.from_amount + 1) * slab.percent_deduction * 0.01
				continue
			if income >= slab.from_amount and income < slab.to_amount:
				t += (income - slab.from_amount + 1) * slab.percent_deduction * 0.01
			elif income >= slab.from_amount and income >= slab.to_amount:
				t += (slab.to_amount - slab.from_amount + 1) * slab.percent_deduction * 0.01
		return t

	is_new_regime = not cint(tax_slab.get("allow_tax_exemption"))
	surcharge = _calculate_surcharge(tax_amount, annual_taxable_earning, is_new_regime, _slab_tax)
	return tax_amount + surcharge, surcharge


def _calculate_surcharge(base_tax, total_income, is_new_regime, slab_tax_fn):
	"""Surcharge on income tax (FY 2025-26), with marginal relief.

	Rates by total income: >₹50L 10%, >₹1Cr 15%, >₹2Cr 25%, >₹5Cr 37%. Under
	the NEW regime the surcharge is capped at 25% (the 37% tier does not apply).
	Marginal relief caps the combined (tax + surcharge) so it never exceeds the
	amount at the threshold plus the income earned beyond it. ``slab_tax_fn``
	recomputes the pre-surcharge slab tax at an arbitrary income (for the
	threshold comparison)."""
	if base_tax <= 0:
		return 0.0
	tiers = [(5000000, 10), (10000000, 15), (20000000, 25), (50000000, 37)]
	if is_new_regime:
		tiers = [(5000000, 10), (10000000, 15), (20000000, 25)]
	rate = prev_rate = threshold = 0.0
	for thr, r in tiers:
		if total_income > thr:
			prev_rate = rate
			rate, threshold = float(r), float(thr)
	if not rate:
		return 0.0
	surcharge = base_tax * rate / 100.0
	# Marginal relief against the threshold (taxed at the previous tier's rate).
	tax_at_threshold = slab_tax_fn(threshold)
	surcharge_at_threshold = tax_at_threshold * prev_rate / 100.0
	max_total = tax_at_threshold + surcharge_at_threshold + (total_income - threshold)
	if base_tax + surcharge > max_total:
		surcharge = max(max_total - base_tax, 0.0)
	return surcharge
