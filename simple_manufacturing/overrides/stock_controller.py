from erpnext.controllers.stock_controller import StockController

class CustomStockController(StockController):

    def update_bundle_details(self, bundle_details, table_name, row, is_rejected=False):
		from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos

		frappe.throw("ok")

		# Since qty field is different for different doctypes
		qty = row.get("qty")
		warehouse = row.get("warehouse")

		if table_name == "packed_items":
			type_of_transaction = "Inward"
			if not self.is_return:
				type_of_transaction = "Outward"
		elif table_name == "supplied_items":
			qty = row.consumed_qty
			warehouse = self.supplier_warehouse
			type_of_transaction = "Outward"
			if self.is_return:
				type_of_transaction = "Inward"
		else:
			type_of_transaction = get_type_of_transaction(self, row)

		if hasattr(row, "stock_qty"):
			qty = row.stock_qty

		if self.doctype == "Stock Entry":
			qty = row.transfer_qty
			warehouse = row.s_warehouse or row.t_warehouse

		serial_nos = row.serial_no
		if is_rejected:
			serial_nos = row.get("rejected_serial_no")
			type_of_transaction = "Inward" if not self.is_return else "Outward"
			qty = row.get("rejected_qty")
			warehouse = row.get("rejected_warehouse")

		if (
			self.is_internal_transfer()
			and self.doctype in ["Sales Invoice", "Delivery Note"]
			and self.is_return
		):
			warehouse = row.get("target_warehouse") or row.get("warehouse")
			type_of_transaction = "Outward"

		bundle_details.update(
			{
				"qty": qty,
				"is_rejected": is_rejected,
				"type_of_transaction": type_of_transaction,
				"warehouse": warehouse,
				"batches": frappe._dict({row.batch_no: qty}) if row.batch_no else None,
				"serial_nos": get_serial_nos(serial_nos) if serial_nos else None,
				"batch_no": row.batch_no,
			}
		)

		custom_use_second_unit = frappe.db.get_value('Item', row.get("item"), 'custom_use_second_unit')
		if cint(custom_use_second_unit) == 1:
			if row.custom_alternate_qty:
				custom_alternate_qty = row.custom_alternate_qty
				bundle_details.update(
					{
						"custom_alternate_qty": custom_alternate_qty,
					}
				)
        