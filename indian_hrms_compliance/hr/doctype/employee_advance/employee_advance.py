# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Abs, Sum
from frappe.utils import add_months, flt, get_first_day, get_link_to_form, getdate, nowdate

import erpnext
from erpnext.accounts.doctype.journal_entry.journal_entry import get_default_bank_cash_account

import indian_hrms_compliance
from indian_hrms_compliance.hr.utils import validate_active_employee


class EmployeeAdvanceOverPayment(frappe.ValidationError):
	pass


class EmployeeAdvance(Document):
	def onload(self):
		self.get("__onload").make_payment_via_journal_entry = frappe.db.get_single_value(
			"Accounts Settings", "make_payment_via_journal_entry"
		)

	def validate(self):
		validate_active_employee(self.employee)
		if not self.get("approval_status"):
			self.approval_status = "Draft"
		self.validate_exchange_rate()
		self.validate_advance_account_type()
		self.set_status()
		self.set_pending_amount()

	def _is_hr_employee(self) -> bool:
		"""True if the requester's user holds an HR role — so their own advance
		routes to their reporting manager instead of HR (no self-approval)."""
		user = frappe.db.get_value("Employee", self.employee, "user_id") if self.employee else None
		return bool(user and (set(frappe.get_roles(user)) & {"HR Manager", "HR User"}))

	def resolve_approver(self):
		"""HR approves by default; if the REQUESTER is HR, route to their reporting
		manager (segregation of duties). None = the HR pool."""
		if self._is_hr_employee():
			mgr = frappe.db.get_value("Employee", self.employee, "reports_to")
			return frappe.db.get_value("Employee", mgr, "user_id") if mgr else None
		return None

	def before_submit(self):
		# Approval gate: an advance can only be submitted once Approved (approval
		# submits it via the inbox). Blocks anyone self-submitting on the Desk.
		if self.get("approval_status") != "Approved":
			frappe.throw(
				_("This advance must be Approved before it can be submitted."),
				title=_("Approval Required"),
			)
		if not self.get("advance_account"):
			default_advance_account = frappe.db.get_value(
				"Company", self.company, "default_employee_advance_account"
			)
			if default_advance_account:
				self.advance_account = default_advance_account
			else:
				frappe.throw(
					_(
						'Advance Account is mandatory. Please set the <a href="/app/company/{0}#default_employee_advance_account" target="_blank">Default Employee Advance Account</a> in the Company record {0} and submit this document.'
					).format(self.company),
					title=_("Missing Advance Account"),
				)

	def on_cancel(self):
		self.ignore_linked_doctypes = ("GL Entry", "Payment Ledger Entry", "Advance Payment Ledger Entry")
		self.check_linked_payment_entry()
		self.set_status(update=True)

	def on_update(self):
		self.publish_update()

	def after_delete(self):
		self.publish_update()

	def publish_update(self):
		employee_user = frappe.db.get_value("Employee", self.employee, "user_id", cache=True)
		indian_hrms_compliance.refetch_resource("indian_hrms_compliance:employee_advance_balance", employee_user)

	def validate_exchange_rate(self):
		if not self.exchange_rate:
			frappe.throw(_("Exchange Rate cannot be zero."))

	def validate_advance_account_type(self):
		if not self.advance_account:
			return

		account_type = frappe.db.get_value("Account", self.advance_account, "account_type")
		if not account_type or (account_type != "Receivable"):
			frappe.throw(
				_("Employee advance account {0} should be of type {1}.").format(
					get_link_to_form("Account", self.advance_account), frappe.bold("Receivable")
				)
			)

	def set_status(self, update=False):
		precision = self.precision("paid_amount")
		total_amount = flt(flt(self.claimed_amount) + flt(self.return_amount), precision)
		status = None

		if self.docstatus == 0:
			status = "Draft"
		elif self.docstatus == 1:
			if flt(self.claimed_amount) > 0 and flt(self.claimed_amount, precision) == flt(
				self.paid_amount, precision
			):
				status = "Claimed"
			elif flt(self.return_amount) > 0 and flt(self.return_amount, precision) == flt(
				self.paid_amount, precision
			):
				status = "Returned"
			elif (
				flt(self.claimed_amount) > 0
				and (flt(self.return_amount) > 0)
				and total_amount == flt(self.paid_amount, precision)
			):
				status = "Partly Claimed and Returned"
			elif flt(self.paid_amount) > 0 and flt(self.advance_amount, precision) == flt(
				self.paid_amount, precision
			):
				status = "Paid"
			else:
				status = "Unpaid"
		elif self.docstatus == 2:
			status = "Cancelled"

		if update:
			self.db_set("status", status)
			self.publish_update()
			self.notify_update()
		else:
			self.status = status

	def set_total_advance_paid(self):
		aple = frappe.qb.DocType("Advance Payment Ledger Entry")

		account_type, account_curreny = frappe.get_value(
			"Account", self.advance_account, ["account_type", "account_currency"]
		)

		company_currency = frappe.get_value("Company", self.company, "default_currency")

		if account_type == "Receivable":
			paid_amount_condition = aple.amount > 0
			returned_amount_condition = aple.amount < 0
		elif account_type == "Payable":
			paid_amount_condition = aple.amount < 0
			returned_amount_condition = aple.amount > 0
		else:
			frappe.throw(
				_("Employee advance account {0} should be of type {1}").format(
					frappe.bold(self.advance_account), frappe.bold("Receivable")
				)
			)

		paid_amount = (
			frappe.qb.from_(aple)
			.select(Abs(Sum(aple.amount)).as_("paid_amount"))
			.where(
				(aple.company == self.company)
				& (aple.delinked == 0)
				& (aple.against_voucher_type == self.doctype)
				& (aple.against_voucher_no == self.name)
				& (paid_amount_condition)
			)
		).run(as_dict=True)[0].paid_amount or 0
		return_amount = (
			frappe.qb.from_(aple)
			.select(Abs(Sum(aple.amount)).as_("return_amount"))
			.where(
				(aple.company == self.company)
				& (aple.delinked == 0)
				& (aple.against_voucher_type == self.doctype)
				& (aple.against_voucher_no == self.name)
				& (returned_amount_condition)
			)
		).run(as_dict=True)[0].return_amount or 0

		if company_currency != self.currency and account_curreny == company_currency:
			paid_amount = flt(paid_amount) / flt(self.exchange_rate)
			return_amount = flt(return_amount) / flt(self.exchange_rate)

		precision = self.precision("paid_amount")
		paid_amount = flt(paid_amount, precision)
		if paid_amount > flt(self.advance_amount, precision):
			frappe.throw(
				_("Row {0}# Paid Amount cannot be greater than requested advance amount"),
				EmployeeAdvanceOverPayment,
			)

		precision = self.precision("return_amount")
		return_amount = flt(return_amount, precision)

		if return_amount > 0 and return_amount > flt(paid_amount - self.claimed_amount, precision):
			frappe.throw(_("Return amount cannot be greater than unclaimed amount"))

		self.db_set("paid_amount", paid_amount)
		self.db_set("return_amount", return_amount)
		self.set_status(update=True)

	def update_claimed_amount(self):
		claimed_amount = (
			frappe.db.sql(
				"""
			SELECT sum(ifnull(allocated_amount, 0))
			FROM `tabExpense Claim Advance` eca, `tabExpense Claim` ec
			WHERE
				eca.employee_advance = %s
				AND ec.approval_status="Approved"
				AND ec.name = eca.parent
				AND ec.docstatus=1
				AND eca.allocated_amount > 0
		""",
				self.name,
			)[0][0]
			or 0
		)

		frappe.db.set_value("Employee Advance", self.name, "claimed_amount", flt(claimed_amount))
		self.reload()
		self.set_status(update=True)

	def set_pending_amount(self):
		Advance = frappe.qb.DocType("Employee Advance")
		self.pending_amount = (
			frappe.qb.from_(Advance)
			.select(Sum(Advance.advance_amount - Advance.paid_amount))
			.where(
				(Advance.employee == self.employee)
				& (Advance.docstatus == 1)
				& (Advance.posting_date <= self.posting_date)
				& (Advance.status == "Unpaid")
			)
		).run()[0][0] or 0.0

	def check_linked_payment_entry(self):
		from erpnext.accounts.utils import (
			remove_ref_doc_link_from_pe,
			update_accounting_ledgers_after_reference_removal,
		)

		if frappe.db.get_single_value("HR Settings", "unlink_payment_on_cancellation_of_employee_advance"):
			remove_ref_doc_link_from_pe(self.doctype, self.name)
			update_accounting_ledgers_after_reference_removal(self.doctype, self.name)


@frappe.whitelist()
def make_bank_entry(dt, dn):
	doc = frappe.get_doc(dt, dn)
	payment_account = get_default_bank_cash_account(
		doc.company, account_type="Cash", mode_of_payment=doc.mode_of_payment
	)
	if not payment_account:
		frappe.throw(_("Please set a Default Cash Account in Company defaults"))

	advance_account_currency = frappe.db.get_value("Account", doc.advance_account, "account_currency")

	advance_amount, advance_exchange_rate = get_advance_amount_advance_exchange_rate(
		advance_account_currency, doc
	)

	paying_amount, paying_exchange_rate = get_paying_amount_paying_exchange_rate(payment_account, doc)

	je = frappe.new_doc("Journal Entry")
	je.posting_date = nowdate()
	je.voucher_type = "Bank Entry"
	je.company = doc.company
	je.remark = "Payment against Employee Advance: " + dn + "\n" + doc.purpose
	je.multi_currency = 1 if advance_account_currency != payment_account.account_currency else 0

	je.append(
		"accounts",
		{
			"account": doc.advance_account,
			"account_currency": advance_account_currency,
			"exchange_rate": flt(advance_exchange_rate),
			"debit_in_account_currency": flt(advance_amount),
			"reference_type": "Employee Advance",
			"reference_name": doc.name,
			"party_type": "Employee",
			"cost_center": erpnext.get_default_cost_center(doc.company),
			"party": doc.employee,
			"is_advance": "Yes",
		},
	)

	je.append(
		"accounts",
		{
			"account": payment_account.account,
			"cost_center": erpnext.get_default_cost_center(doc.company),
			"credit_in_account_currency": flt(paying_amount),
			"account_currency": payment_account.account_currency,
			"account_type": payment_account.account_type,
			"exchange_rate": flt(paying_exchange_rate),
		},
	)

	return je.as_dict()


def get_advance_amount_advance_exchange_rate(advance_account_currency, doc):
	if advance_account_currency != doc.currency:
		advance_amount = flt(doc.advance_amount) * flt(doc.exchange_rate)
		advance_exchange_rate = 1
	else:
		advance_amount = doc.advance_amount
		advance_exchange_rate = doc.exchange_rate

	return advance_amount, advance_exchange_rate


def get_paying_amount_paying_exchange_rate(payment_account, doc):
	if payment_account.account_currency != doc.currency:
		paying_amount = flt(doc.advance_amount) * flt(doc.exchange_rate)
		paying_exchange_rate = 1
	else:
		paying_amount = doc.advance_amount
		paying_exchange_rate = doc.exchange_rate

	return paying_amount, paying_exchange_rate


@frappe.whitelist()
@frappe.whitelist()
def submit_advance_for_approval(name):
	"""Send a draft advance for approval — resolves the approver (HR, or the
	requester's reporting manager when the requester is HR) and marks it Pending."""
	doc = frappe.get_doc("Employee Advance", name)
	if doc.docstatus != 0 or doc.approval_status not in ("Draft", "Rejected", "Needs Clarification"):
		frappe.throw(_("Only a draft advance can be sent for approval."))
	doc.approver = doc.resolve_approver()
	doc.approval_status = "Pending Approval"
	doc.clarification_note = None
	doc.save()
	return {"approval_status": doc.approval_status, "approver": doc.approver}


def create_return_through_additional_salary(doc):
	import json

	if isinstance(doc, str):
		doc = frappe._dict(json.loads(doc))

	additional_salary = frappe.new_doc("Additional Salary")
	additional_salary.employee = doc.employee
	additional_salary.currency = doc.currency
	additional_salary.overwrite_salary_structure_amount = 0
	additional_salary.amount = doc.paid_amount - doc.claimed_amount
	additional_salary.company = doc.company
	additional_salary.ref_doctype = doc.doctype
	additional_salary.ref_docname = doc.name

	return additional_salary


_RECOVERY_MONTHS = {
	"Single (Next Salary)": 1,
	"3 Monthly Installments": 3,
	"6 Monthly Installments": 6,
}
_ADVANCE_RECOVERY_COMPONENT = "Advance Recovery"


def _ensure_advance_recovery_component(company: str) -> str:
	"""Get-or-create the 'Advance Recovery' Deduction component and point its
	per-company account at that company's Employee Advances receivable, so a
	recovery deduction CLEARS the advance instead of crediting a payable. Fixed
	amount (not prorated), non-taxable."""
	name = _ADVANCE_RECOVERY_COMPONENT
	if not frappe.db.exists("Salary Component", name):
		frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": name,
				"salary_component_abbr": "AR",
				"type": "Deduction",
				"depends_on_payment_days": 0,
				"is_tax_applicable": 0,
				"description": "Recovery of an Employee Advance from salary. Books against the "
				"company's Employee Advances receivable (not a payable), clearing the advance.",
			}
		).insert(ignore_permissions=True)

	# Map each company's row to its Employee Advances account (overrides the
	# generic '<Component> Payable' default the account sync would otherwise fill).
	comp = frappe.get_doc("Salary Component", name)
	changed = False
	for row in comp.get("accounts") or []:
		abbr = frappe.get_cached_value("Company", row.company, "abbr")
		adv_account = f"Employee Advances - {abbr}"
		if row.account != adv_account and frappe.db.exists("Account", adv_account):
			row.account = adv_account
			changed = True
	if changed:
		comp.save(ignore_permissions=True)
	return name


@frappe.whitelist()
def schedule_salary_recovery(name: str, quiet: bool = False) -> dict:
	"""Create the Advance Recovery salary deductions for the chosen plan (1 / 3 /
	6 equal monthly installments). Each is an Additional Salary deduction that
	references this advance, so payroll books it against the advance account and
	each salary slip auto-picks it up. Refuses to double-schedule."""
	doc = frappe.get_doc("Employee Advance", name)
	if doc.docstatus != 1:
		frappe.throw(_("Submit the advance first."))
	months = _RECOVERY_MONTHS.get(doc.get("salary_recovery_plan"))
	if not months:
		frappe.throw(_("Select a Salary Recovery Plan first."))

	pending = flt(doc.paid_amount) - flt(doc.claimed_amount) - flt(doc.return_amount)
	if pending <= 0:
		frappe.throw(_("Nothing to recover — the advance is unpaid or fully claimed/returned."))

	if frappe.db.count(
		"Additional Salary",
		{"ref_doctype": "Employee Advance", "ref_docname": name, "docstatus": 1},
	):
		frappe.throw(_("Salary recovery is already scheduled for this advance."))

	component = _ensure_advance_recovery_component(doc.company)
	start = getdate(doc.get("recovery_start_date") or add_months(nowdate(), 1))
	# Equal split; the last installment absorbs the rounding remainder.
	per = flt(pending / months, 2)
	amounts = [per] * (months - 1) + [flt(pending - per * (months - 1), 2)]

	created = []
	for k, amt in enumerate(amounts):
		add_sal = frappe.new_doc("Additional Salary")
		add_sal.employee = doc.employee
		add_sal.company = doc.company
		add_sal.currency = doc.currency
		add_sal.salary_component = component
		add_sal.amount = amt
		add_sal.payroll_date = get_first_day(add_months(start, k))
		add_sal.ref_doctype = "Employee Advance"
		add_sal.ref_docname = name
		add_sal.overwrite_salary_structure_amount = 0
		add_sal.insert(ignore_permissions=True)
		add_sal.submit()
		created.append(add_sal.name)

	frappe.db.set_value(
		"Employee Advance", name, "repay_unclaimed_amount_from_salary", 1, update_modified=False
	)
	if not quiet:
		frappe.msgprint(
			_("Scheduled {0} recovery deduction(s) totalling {1}.").format(len(created), pending)
		)
	return {"created": created, "total": pending, "months": months}


def ensure_recoveries_scheduled(employees, company, period_start):
	"""Auto-schedule Advance Recovery installments for a payroll run — no manual
	'Schedule Salary Recovery' click needed. For each employee's SUBMITTED advances
	that opted into salary recovery (a Salary Recovery Plan is chosen) and still have
	a pending balance and aren't already scheduled, create the recovery deductions so
	the slips pick them up. Idempotent (skips already-scheduled) and defensive (one
	bad advance never blocks the run). Returns the list of advances scheduled."""
	scheduled = []
	for employee in dict.fromkeys(e for e in employees if e):  # de-dup, preserve order
		advances = frappe.get_all(
			"Employee Advance",
			filters={"employee": employee, "company": company, "docstatus": 1},
			fields=["name", "salary_recovery_plan", "paid_amount", "claimed_amount",
				"return_amount", "recovery_start_date"],
		)
		for adv in advances:
			# Opt-in signal: the advance carries a recovery plan.
			if not adv.salary_recovery_plan:
				continue
			pending = flt(adv.paid_amount) - flt(adv.claimed_amount) - flt(adv.return_amount)
			if pending <= 0:
				continue
			# Already scheduled? leave it (don't double up the cycle).
			if frappe.db.count(
				"Additional Salary",
				{"ref_doctype": "Employee Advance", "ref_docname": adv.name, "docstatus": 1},
			):
				continue
			# Align the cycle to this payroll month if the advance has no explicit start.
			if not adv.recovery_start_date:
				frappe.db.set_value(
					"Employee Advance", adv.name, "recovery_start_date", period_start, update_modified=False
				)
			try:
				schedule_salary_recovery(adv.name, quiet=True)
				scheduled.append(adv.name)
			except Exception:
				frappe.log_error(
					title=f"Auto advance-recovery scheduling failed: {adv.name}",
					message=frappe.get_traceback(),
				)
	return scheduled


@frappe.whitelist()
def make_return_entry(
	employee,
	company,
	employee_advance_name,
	return_amount,
	advance_account,
	currency,
	exchange_rate,
	mode_of_payment=None,
):
	bank_cash_account = get_default_bank_cash_account(
		company, account_type="Cash", mode_of_payment=mode_of_payment
	)
	if not bank_cash_account:
		frappe.throw(_("Please set a Default Cash Account in Company defaults"))

	advance_account_currency = frappe.db.get_value("Account", advance_account, "account_currency")

	je = frappe.new_doc("Journal Entry")
	je.posting_date = nowdate()
	je.voucher_type = get_voucher_type(mode_of_payment)
	je.company = company
	je.remark = "Return against Employee Advance: " + employee_advance_name
	je.multi_currency = 1 if advance_account_currency != bank_cash_account.account_currency else 0

	advance_account_amount = (
		flt(return_amount)
		if advance_account_currency == currency
		else flt(return_amount) * flt(exchange_rate)
	)

	je.append(
		"accounts",
		{
			"account": advance_account,
			"credit_in_account_currency": advance_account_amount,
			"account_currency": advance_account_currency,
			"exchange_rate": flt(exchange_rate) if advance_account_currency == currency else 1,
			"reference_type": "Employee Advance",
			"reference_name": employee_advance_name,
			"party_type": "Employee",
			"party": employee,
			"is_advance": "Yes",
			"cost_center": erpnext.get_default_cost_center(company),
		},
	)

	bank_amount = (
		flt(return_amount)
		if bank_cash_account.account_currency == currency
		else flt(return_amount) * flt(exchange_rate)
	)

	je.append(
		"accounts",
		{
			"account": bank_cash_account.account,
			"debit_in_account_currency": bank_amount,
			"account_currency": bank_cash_account.account_currency,
			"account_type": bank_cash_account.account_type,
			"exchange_rate": flt(exchange_rate) if bank_cash_account.account_currency == currency else 1,
			"cost_center": erpnext.get_default_cost_center(company),
		},
	)

	return je.as_dict()


def get_voucher_type(mode_of_payment=None):
	voucher_type = "Cash Entry"

	if mode_of_payment:
		mode_of_payment_type = frappe.get_cached_value("Mode of Payment", mode_of_payment, "type")
		if mode_of_payment_type == "Bank":
			voucher_type = "Bank Entry"

	return voucher_type
