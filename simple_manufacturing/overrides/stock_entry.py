from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry

class CustomStockEntry(StockEntry):
    def before_save(self):
        for i in self.items:
            custom_use_second_unit = frappe.db.get_value('Item', i.item_code, 'custom_use_second_unit')
            if cint(custom_use_second_unit) == 1:
                if flt(i.custom_alternate_qty) <= 0.0:
                    frappe.throw("Fill the alternative quantity!")

        if not bool(self.custom_auto_batch_and_serial_number):
            self.make_serial_and_batch_bundle_for_outward()

    #def on_submit(self):
    #    for i in self.items:
    #        custom_use_second_unit = frappe.db.get_value('Item', i.item_code, 'custom_use_second_unit')
    #        if cint(custom_use_second_unit) == 1:
                