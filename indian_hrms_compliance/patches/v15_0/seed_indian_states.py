# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Seed Indian State + PT slabs — Phase 6A.

Idempotent: existing rows have their fields refreshed (not re-inserted),
existing PT slabs are wiped and replaced from the spec.

Rate references (verified for 2026):
  - Karnataka: PT ₹0 up to ₹24,999; ₹200/mo if ≥₹25,000 (₹300 in Feb).
  - Maharashtra: gender-specific. Male >₹10k → ₹200/mo (₹300 Feb).
    Women up to ₹25k exempt.
  - Tamil Nadu: half-yearly (Aug + Jan), ₹100–₹1,250 per half-year.
  - Andhra Pradesh / Telangana: Nil up to ₹15k; ₹150 at ₹15–20k;
    ₹200 above ₹20k. Monthly.
  - Delhi: NO PT.
  - UP / Uttarakhand: NO PT.
  - West Bengal: ₹0 up to ₹10k; ₹110 at ₹10–15k; ₹130 at ₹15–25k;
    ₹150 at ₹25–40k; ₹200 above ₹40k. Monthly.
  - Kerala: half-yearly slabs.
"""

import frappe


STATES = [
	{
		"state_code": "KA",
		"state_name": "Karnataka",
		"region": "South",
		"pt_applicable": 1,
		"pt_filing_frequency": "Monthly",
		"pt_special_month": "February (extra)",
		"pt_max_annual_cap": 2500,
		"lwf_applicable": 1,
		"lwf_filing_frequency": "Annual",
		"lwf_employee_amount": 40,
		"lwf_employer_amount": 20,
		"shops_estab_act_name": "Karnataka Shops and Commercial Establishments Act, 1961",
		"shops_estab_annual_return_form": "Form U",
		"shops_estab_annual_return_due": "31 Jan",
		"shops_estab_certificate_validity": "5 years",
		"labour_code_notification_status": "Partial",
		"pt_slabs": [
			{"gender": "Any", "from_amount": 0, "to_amount": 24999, "period": "Monthly", "amount": 0, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 25000, "to_amount": 0, "period": "Monthly", "amount": 200, "special_month_amount": 300, "effective_from": "2026-04-01"},
		],
	},
	{
		"state_code": "MH",
		"state_name": "Maharashtra",
		"region": "West",
		"pt_applicable": 1,
		"pt_filing_frequency": "Monthly",
		"pt_special_month": "February (extra)",
		"pt_max_annual_cap": 2500,
		"lwf_applicable": 1,
		"lwf_filing_frequency": "Half-yearly",
		"lwf_employee_amount": 6,
		"lwf_employer_amount": 18,
		"shops_estab_act_name": "Maharashtra Shops and Establishments (Regulation of Employment and Conditions of Service) Act, 2017",
		"shops_estab_annual_return_form": "Form R",
		"shops_estab_annual_return_due": "Renewal annually",
		"shops_estab_certificate_validity": "1 year",
		"labour_code_notification_status": "Partial",
		"pt_slabs": [
			{"gender": "Female", "from_amount": 0, "to_amount": 25000, "period": "Monthly", "amount": 0, "effective_from": "2026-04-01"},
			{"gender": "Female", "from_amount": 25001, "to_amount": 0, "period": "Monthly", "amount": 200, "special_month_amount": 300, "effective_from": "2026-04-01"},
			{"gender": "Male", "from_amount": 0, "to_amount": 10000, "period": "Monthly", "amount": 0, "effective_from": "2026-04-01"},
			{"gender": "Male", "from_amount": 10001, "to_amount": 0, "period": "Monthly", "amount": 200, "special_month_amount": 300, "effective_from": "2026-04-01"},
		],
	},
	{
		"state_code": "DL",
		"state_name": "Delhi",
		"region": "North",
		"pt_applicable": 0,
		"pt_max_annual_cap": 0,
		"lwf_applicable": 0,
		"shops_estab_act_name": "Delhi Shops and Establishments Act, 1954",
		"shops_estab_annual_return_form": "Form G",
		"shops_estab_annual_return_due": "Renewal as per notification",
		"shops_estab_certificate_validity": "Lifetime",
		"labour_code_notification_status": "None Notified",
		"notes": "Delhi does NOT levy Professional Tax. Labour Welfare Fund also not notified.",
		"pt_slabs": [],
	},
	{
		"state_code": "TN",
		"state_name": "Tamil Nadu",
		"region": "South",
		"pt_applicable": 1,
		"pt_filing_frequency": "Half-yearly",
		"pt_max_annual_cap": 2500,
		"lwf_applicable": 1,
		"lwf_filing_frequency": "Annual",
		"lwf_employee_amount": 20,
		"lwf_employer_amount": 40,
		"shops_estab_act_name": "Tamil Nadu Shops and Establishments Act, 1947",
		"shops_estab_annual_return_form": "Form R",
		"shops_estab_annual_return_due": "31 Jan",
		"shops_estab_certificate_validity": "1 year",
		"labour_code_notification_status": "Partial",
		"pt_slabs": [
			{"gender": "Any", "from_amount": 0, "to_amount": 21000, "period": "Half-yearly", "amount": 0, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 21001, "to_amount": 30000, "period": "Half-yearly", "amount": 135, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 30001, "to_amount": 45000, "period": "Half-yearly", "amount": 315, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 45001, "to_amount": 60000, "period": "Half-yearly", "amount": 690, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 60001, "to_amount": 75000, "period": "Half-yearly", "amount": 1025, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 75001, "to_amount": 0, "period": "Half-yearly", "amount": 1250, "effective_from": "2026-04-01"},
		],
	},
	{
		"state_code": "GJ",
		"state_name": "Gujarat",
		"region": "West",
		"pt_applicable": 1,
		"pt_filing_frequency": "Monthly",
		"pt_max_annual_cap": 2500,
		"lwf_applicable": 1,
		"lwf_filing_frequency": "Half-yearly",
		"lwf_employee_amount": 6,
		"lwf_employer_amount": 12,
		"shops_estab_act_name": "Gujarat Shops and Establishments (Regulation of Employment and Conditions of Service) Act, 2019",
		"shops_estab_annual_return_form": "Form K",
		"shops_estab_annual_return_due": "30 Apr",
		"shops_estab_certificate_validity": "1 year",
		"labour_code_notification_status": "Partial",
		"pt_slabs": [
			{"gender": "Any", "from_amount": 0, "to_amount": 11999, "period": "Monthly", "amount": 0, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 12000, "to_amount": 0, "period": "Monthly", "amount": 200, "effective_from": "2026-04-01"},
		],
	},
	{
		"state_code": "AP",
		"state_name": "Andhra Pradesh",
		"region": "South",
		"pt_applicable": 1,
		"pt_filing_frequency": "Monthly",
		"pt_max_annual_cap": 2500,
		"lwf_applicable": 1,
		"lwf_filing_frequency": "Annual",
		"lwf_employee_amount": 30,
		"lwf_employer_amount": 70,
		"shops_estab_act_name": "Andhra Pradesh Shops and Establishments Act, 1988",
		"shops_estab_annual_return_form": "Form XXII",
		"shops_estab_annual_return_due": "Renewal as per notification",
		"shops_estab_certificate_validity": "1 year",
		"labour_code_notification_status": "Partial",
		"pt_slabs": [
			{"gender": "Any", "from_amount": 0, "to_amount": 14999, "period": "Monthly", "amount": 0, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 15000, "to_amount": 19999, "period": "Monthly", "amount": 150, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 20000, "to_amount": 0, "period": "Monthly", "amount": 200, "effective_from": "2026-04-01"},
		],
	},
	{
		"state_code": "TS",
		"state_name": "Telangana",
		"region": "South",
		"pt_applicable": 1,
		"pt_filing_frequency": "Monthly",
		"pt_max_annual_cap": 2500,
		"lwf_applicable": 1,
		"lwf_filing_frequency": "Annual",
		"lwf_employee_amount": 2,
		"lwf_employer_amount": 5,
		"shops_estab_act_name": "Telangana Shops and Establishments Act, 1988",
		"shops_estab_annual_return_form": "Form XXII",
		"shops_estab_annual_return_due": "Renewal as per notification",
		"shops_estab_certificate_validity": "1 year",
		"labour_code_notification_status": "Partial",
		"pt_slabs": [
			{"gender": "Any", "from_amount": 0, "to_amount": 14999, "period": "Monthly", "amount": 0, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 15000, "to_amount": 19999, "period": "Monthly", "amount": 150, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 20000, "to_amount": 0, "period": "Monthly", "amount": 200, "effective_from": "2026-04-01"},
		],
	},
	{
		"state_code": "WB",
		"state_name": "West Bengal",
		"region": "East",
		"pt_applicable": 1,
		"pt_filing_frequency": "Monthly",
		"pt_max_annual_cap": 2500,
		"lwf_applicable": 1,
		"lwf_filing_frequency": "Half-yearly",
		"lwf_employee_amount": 3,
		"lwf_employer_amount": 15,
		"shops_estab_act_name": "West Bengal Shops and Establishments Act, 1963",
		"shops_estab_annual_return_form": "Form M",
		"shops_estab_annual_return_due": "31 Jan",
		"shops_estab_certificate_validity": "1 year",
		"labour_code_notification_status": "Partial",
		"pt_slabs": [
			{"gender": "Any", "from_amount": 0, "to_amount": 10000, "period": "Monthly", "amount": 0, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 10001, "to_amount": 15000, "period": "Monthly", "amount": 110, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 15001, "to_amount": 25000, "period": "Monthly", "amount": 130, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 25001, "to_amount": 40000, "period": "Monthly", "amount": 150, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 40001, "to_amount": 0, "period": "Monthly", "amount": 200, "effective_from": "2026-04-01"},
		],
	},
	{
		"state_code": "HR",
		"state_name": "Haryana",
		"region": "North",
		"pt_applicable": 0,
		"pt_max_annual_cap": 0,
		"lwf_applicable": 1,
		"lwf_filing_frequency": "Annual",
		"lwf_employee_amount": 31,
		"lwf_employer_amount": 62,
		"shops_estab_act_name": "Punjab Shops and Commercial Establishments Act, 1958 (as adopted)",
		"shops_estab_annual_return_form": "Form F",
		"shops_estab_annual_return_due": "Renewal as per notification",
		"shops_estab_certificate_validity": "1 year",
		"labour_code_notification_status": "Partial",
		"notes": "Haryana does NOT levy Professional Tax (PT was struck down by Punjab & Haryana HC in 2018).",
		"pt_slabs": [],
	},
	{
		"state_code": "PB",
		"state_name": "Punjab",
		"region": "North",
		"pt_applicable": 1,
		"pt_filing_frequency": "Monthly",
		"pt_max_annual_cap": 2400,
		"lwf_applicable": 1,
		"lwf_filing_frequency": "Annual",
		"lwf_employee_amount": 5,
		"lwf_employer_amount": 20,
		"shops_estab_act_name": "Punjab Shops and Commercial Establishments Act, 1958",
		"shops_estab_annual_return_form": "Form F",
		"shops_estab_annual_return_due": "Renewal as per notification",
		"shops_estab_certificate_validity": "1 year",
		"labour_code_notification_status": "Partial",
		"pt_slabs": [
			{"gender": "Any", "from_amount": 0, "to_amount": 0, "period": "Monthly", "amount": 200, "effective_from": "2026-04-01"},
		],
	},
	{
		"state_code": "KL",
		"state_name": "Kerala",
		"region": "South",
		"pt_applicable": 1,
		"pt_filing_frequency": "Half-yearly",
		"pt_max_annual_cap": 2500,
		"lwf_applicable": 1,
		"lwf_filing_frequency": "Annual",
		"lwf_employee_amount": 50,
		"lwf_employer_amount": 50,
		"shops_estab_act_name": "Kerala Shops and Commercial Establishments Act, 1960",
		"shops_estab_annual_return_form": "Form U",
		"shops_estab_annual_return_due": "31 Jan",
		"shops_estab_certificate_validity": "1 year",
		"labour_code_notification_status": "Partial",
		"pt_slabs": [
			{"gender": "Any", "from_amount": 0, "to_amount": 11999, "period": "Half-yearly", "amount": 0, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 12000, "to_amount": 17999, "period": "Half-yearly", "amount": 120, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 18000, "to_amount": 29999, "period": "Half-yearly", "amount": 180, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 30000, "to_amount": 44999, "period": "Half-yearly", "amount": 300, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 45000, "to_amount": 59999, "period": "Half-yearly", "amount": 450, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 60000, "to_amount": 74999, "period": "Half-yearly", "amount": 600, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 75000, "to_amount": 99999, "period": "Half-yearly", "amount": 750, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 100000, "to_amount": 124999, "period": "Half-yearly", "amount": 1000, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 125000, "to_amount": 0, "period": "Half-yearly", "amount": 1250, "effective_from": "2026-04-01"},
		],
	},
	{
		"state_code": "UP",
		"state_name": "Uttar Pradesh",
		"region": "North",
		"pt_applicable": 0,
		"pt_max_annual_cap": 0,
		"lwf_applicable": 0,
		"shops_estab_act_name": "Uttar Pradesh Dookan Aur Vanijya Adhishthan Adhiniyam, 1962",
		"shops_estab_annual_return_form": "Form C",
		"shops_estab_annual_return_due": "Renewal as per notification",
		"shops_estab_certificate_validity": "1 year",
		"labour_code_notification_status": "None Notified",
		"notes": "Uttar Pradesh does NOT levy Professional Tax. LWF also not applicable.",
		"pt_slabs": [],
	},
	{
		"state_code": "MP",
		"state_name": "Madhya Pradesh",
		"region": "Central",
		"pt_applicable": 1,
		"pt_filing_frequency": "Monthly",
		"pt_max_annual_cap": 2500,
		"lwf_applicable": 1,
		"lwf_filing_frequency": "Annual",
		"lwf_employee_amount": 10,
		"lwf_employer_amount": 30,
		"shops_estab_act_name": "Madhya Pradesh Shops and Establishments Act, 1958",
		"shops_estab_annual_return_form": "Form Q",
		"shops_estab_annual_return_due": "Renewal as per notification",
		"shops_estab_certificate_validity": "1 year",
		"labour_code_notification_status": "Partial",
		"pt_slabs": [
			{"gender": "Any", "from_amount": 0, "to_amount": 18750, "period": "Monthly", "amount": 0, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 18751, "to_amount": 25000, "period": "Monthly", "amount": 125, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 25001, "to_amount": 33333, "period": "Monthly", "amount": 167, "effective_from": "2026-04-01"},
			{"gender": "Any", "from_amount": 33334, "to_amount": 0, "period": "Monthly", "amount": 208, "special_month_amount": 212, "effective_from": "2026-04-01"},
		],
	},
]


def execute():
	"""Idempotent: upsert each state and replace its PT slab rows."""
	for spec in STATES:
		slabs = spec.pop("pt_slabs", [])
		state_code = spec["state_code"]
		if frappe.db.exists("Indian State", state_code):
			doc = frappe.get_doc("Indian State", state_code)
			for k, v in spec.items():
				doc.set(k, v)
			# Wipe existing slabs and re-seed
			doc.set("pt_slabs", [])
			for slab in slabs:
				doc.append("pt_slabs", slab)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": "Indian State", **spec})
			for slab in slabs:
				doc.append("pt_slabs", slab)
			doc.insert(ignore_permissions=True)
		# Restore so subsequent re-runs see the same spec
		spec["pt_slabs"] = slabs
	frappe.db.commit()
	print(f"  Seeded / updated {len(STATES)} Indian State records with PT slabs")
