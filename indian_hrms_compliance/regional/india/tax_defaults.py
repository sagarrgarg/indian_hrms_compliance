# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Idempotent seed for India income-tax masters used by the self-service
declaration + regime comparator: standard exemption categories/sub-categories
and an Old-Regime Income Tax Slab (the New-Regime slab is shipped separately).

Safe to re-run — only creates what's missing, never overwrites edits.
"""

import frappe

# category -> (category max, [(sub category, sub max)])
EXEMPTION_CATEGORIES = {
	"80C - Investments": (150000, [
		("Public Provident Fund (PPF)", 150000),
		("Employee Provident Fund (EPF)", 150000),
		("Life Insurance Premium (LIC)", 150000),
		("ELSS Mutual Funds", 150000),
		("5-Year Tax Saving FD", 150000),
		("Sukanya Samriddhi", 150000),
		("Children Tuition Fees", 150000),
		("Home Loan Principal Repayment", 150000),
		("NSC", 150000),
	]),
	"80CCD(1B) - NPS (additional)": (50000, [
		("NPS Self Contribution (80CCD-1B)", 50000),
	]),
	"80D - Medical Insurance": (100000, [
		("Health Insurance - Self & Family", 25000),
		("Health Insurance - Parents", 50000),
		("Preventive Health Check-up", 5000),
	]),
	"Section 24 - Home Loan Interest": (200000, [
		("Home Loan Interest (Self-occupied)", 200000),
	]),
	"80E - Education Loan Interest": (0, [
		("Education Loan Interest (80E)", 0),
	]),
	"80TTA/80TTB - Savings Interest": (10000, [
		("Savings Account Interest (80TTA)", 10000),
	]),
	"80G - Donations": (0, [
		("Donations to Approved Funds (80G)", 0),
	]),
	"HRA": (0, [
		("House Rent Paid (HRA)", 0),
	]),
}

OLD_REGIME_SLAB = "Old Tax Regime (FY 2025-26)"


def seed_tax_exemption_masters():
	created = {"categories": 0, "sub_categories": 0}
	for category, (cat_max, subs) in EXEMPTION_CATEGORIES.items():
		if not frappe.db.exists("Employee Tax Exemption Category", category):
			frappe.get_doc(
				{
					"doctype": "Employee Tax Exemption Category",
					"name": category,
					"max_amount": cat_max,
					"is_active": 1,
				}
			).insert(ignore_permissions=True)
			created["categories"] += 1
		for sub_name, sub_max in subs:
			if not frappe.db.exists("Employee Tax Exemption Sub Category", sub_name):
				frappe.get_doc(
					{
						"doctype": "Employee Tax Exemption Sub Category",
						"name": sub_name,
						"exemption_category": category,
						"max_amount": sub_max,
						"is_active": 1,
					}
				).insert(ignore_permissions=True)
				created["sub_categories"] += 1
	return created


def seed_old_regime_slab():
	"""National Old-Regime Income Tax Slab (FY 2025-26): std deduction 50k,
	87A rebate up to 5L taxable, 4% cess. New-Regime slab ships separately."""
	if frappe.db.exists("Income Tax Slab", OLD_REGIME_SLAB):
		return None
	slab = frappe.get_doc(
		{
			"doctype": "Income Tax Slab",
			"name": OLD_REGIME_SLAB,
			"effective_from": "2025-04-01",
			"company": None,
			"currency": "INR",
			"allow_tax_exemption": 1,
			"standard_tax_exemption_amount": 50000,
			"tax_relief_limit": 500000,
			"slabs": [
				{"from_amount": 250001, "to_amount": 500000, "percent_deduction": 5},
				{"from_amount": 500001, "to_amount": 1000000, "percent_deduction": 20},
				{"from_amount": 1000001, "to_amount": 0, "percent_deduction": 30},
			],
			"other_taxes_and_charges": [
				{"description": "Health & Education Cess", "percent": 4},
			],
		}
	)
	slab.insert(ignore_permissions=True)
	slab.submit()
	return slab.name


def seed_all():
	out = seed_tax_exemption_masters()
	out["old_regime_slab"] = seed_old_regime_slab()
	frappe.db.commit()
	return out
