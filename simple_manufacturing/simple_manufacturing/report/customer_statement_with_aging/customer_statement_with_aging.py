import frappe
import datetime

def execute(filters=None):
	# ============================================================
	# CUSTOMER STATEMENT – SERVER SIDE SCRIPT REPORT
	# ============================================================

	customer = (filters.get("customer") or "").strip()
	from_date = (filters.get("from_date") or "").strip()
	to_date   = (filters.get("to_date") or "").strip()
	company   = (filters.get("company") or "").strip()

	# Guard
	if not customer or not to_date:
		columns = [{"label": "Message", "fieldname": "msg", "fieldtype": "Data", "width": 500}]
		data = [{"msg": "Please select Customer and To Date"}]
		return columns, data

	# ------------------------------------------------------------
	# Columns
	# ------------------------------------------------------------
	columns = [
		{"label": "Document", "fieldname": "document", "fieldtype": "Dynamic Link", "options": "doctype", "width": 120},
		{"label": "BP Ref No", "fieldname": "bp_ref", "fieldtype": "Data", "width": 120},
		{"label": "Posting Date", "fieldname": "post_date", "fieldtype": "Date", "width": 100},
		{"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{"label": "Details", "fieldname": "details", "fieldtype": "Data", "width": 200},
		{"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 120, "options": "currency"},
		{"label": "Balance", "fieldname": "balance", "fieldtype": "Currency", "width": 120, "options": "currency"},
	]

	# ------------------------------------------------------------
	# Helper: Get Outstanding for invoice
	# ------------------------------------------------------------
	def get_outstanding(inv):
		paid = frappe.db.sql("""
			SELECT SUM(amount)
			FROM `tabPayment Ledger Entry`
			WHERE against_voucher_type='Sales Invoice'
			AND against_voucher_no=%s
		""", inv, as_list=True)[0][0] or 0

		grand = frappe.db.get_value("Sales Invoice", inv, "grand_total") or 0
		return grand - paid

	# ------------------------------------------------------------
	# PRIOR PERIOD BALANCE
	# ------------------------------------------------------------
	prior_data = []
	prior_total = 0
	prior_invoices = []

	if from_date:
		prior_invoices = frappe.db.sql("""
			SELECT name, posting_date, due_date, po_no, grand_total
			FROM `tabSales Invoice`
			WHERE customer=%s
			AND company=%s
			AND posting_date < %s
			AND docstatus=1
			ORDER BY posting_date ASC
		""", (customer, company, from_date), as_dict=True)

		running = 0
		for inv in prior_invoices:
			balance = get_outstanding(inv.name)
			running = balance
			prior_total = running

			prior_data.append({
				"document": inv.name,
				"doctype": "Sales Invoice",
				"bp_ref": inv.po_no,
				"post_date": inv.posting_date,
				"due_date": inv.due_date,
				"details": f"A/R Invoice - {customer}",
				"amount": inv.grand_total,
				"balance": running
			})

	# ------------------------------------------------------------
	# CURRENT PERIOD
	# ------------------------------------------------------------
	current_data = []
	current_total = 0
	balance_running = prior_total

	current_invoices = frappe.db.sql("""
		SELECT name, posting_date, due_date, po_no, grand_total
		FROM `tabSales Invoice`
		WHERE customer=%s
		AND company=%s
		AND posting_date BETWEEN %s AND %s
		AND docstatus=1
		ORDER BY posting_date ASC
	""", (customer, company, from_date, to_date), as_dict=True)

	for inv in current_invoices:
		ost = get_outstanding(inv.name)
		balance_running += ost
		current_total += ost

		current_data.append({
			"document": inv.name,
			"doctype": "Sales Invoice",
			"bp_ref": inv.po_no,
			"post_date": inv.posting_date,
			"due_date": inv.due_date,
			"details": f"A/R Invoice - {customer}",
			"amount": inv.grand_total,
			"balance": balance_running
		})

	# ------------------------------------------------------------
	# AGING
	# ------------------------------------------------------------
	today = datetime.datetime.strptime(to_date, "%Y-%m-%d").date()

	aging = {"0_30": 0, "31_60": 0, "61_90": 0, "90_120": 0, "120p": 0}
	all_invoices = prior_invoices + current_invoices

	for inv in all_invoices:
		outstanding = get_outstanding(inv.name)
		if outstanding <= 0:
			continue

		age_days = (today - inv.posting_date).days

		if age_days <= 30:
			aging["0_30"] += outstanding
		elif age_days <= 60:
			aging["31_60"] += outstanding
		elif age_days <= 90:
			aging["61_90"] += outstanding
		elif age_days <= 120:
			aging["90_120"] += outstanding
		else:
			aging["120p"] += outstanding

	# ------------------------------------------------------------
	# FINAL MERGE
	# ------------------------------------------------------------
	data = []

	# Prior period header
	if prior_data:
		data.append({"document": "Prior Period Balance"})
		data.extend(prior_data)

	# Current period header
	if current_data:
		data.append({"document": "Current Period"})
		data.extend(current_data)

	# Totals row
	data.append({
		"document": "Total",
		"amount": prior_total + current_total,
		"balance": balance_running
	})

	# Aging row
	data.append({
		"document": "Aging Summary",
		"details": (
			f"0-30: {aging['0_30']} | "
			f"31-60: {aging['31_60']} | "
			f"61-90: {aging['61_90']} | "
			f"90-120: {aging['90_120']} | "
			f"120+: {aging['120p']}"
		)
	})

	return columns, data
