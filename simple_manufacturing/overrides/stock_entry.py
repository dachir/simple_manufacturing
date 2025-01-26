from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry

class CustomStockEntry(StockEntry):
    def before_save(self):
        if not bool(self.custom_auto_batch_and_serial_number):
            self.make_serial_and_batch_bundle_for_outward()