import frappe
from frappe.utils import cint

def update_stock_ledger_entry(doc, method):
    custom_use_second_unit = frappe.db.get_value('Item', doc.get("item_code"), 'custom_use_second_unit')
    if cint(custom_use_second_unit) == 1:
        child_doctype = f"{doc.voucher_type} Detail" if doc.voucher_type == "Stock Entry" else f"{doc.voucher_type} Item"
        child_entry = frappe.db.sql(
            f"""
            SELECT custom_alternate_qty
            FROM `tab{child_doctype}`
            WHERE name = %s
            """, (doc.voucher_detail_no,), as_dict=1
        )

        if child_entry and child_entry[0].custom_alternate_qty is not None:
            custom_alternate_qty = child_entry[0].get("custom_alternate_qty") if doc.actual_qty > 0 else - child_entry[0].get("custom_alternate_qty")
            doc.custom_alternate_qty = custom_alternate_qty
            doc.db_set("custom_alternate_qty", custom_alternate_qty)
        
