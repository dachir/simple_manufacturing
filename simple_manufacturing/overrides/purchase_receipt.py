from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt

import frappe
from frappe.utils import cint, flt

class CustomPurchaseReceipt(PurchaseReceipt):
    
    def before_save(self):
        for i in self.items:
            custom_use_second_unit = frappe.db.get_value('Item', i.item_code, 'custom_use_second_unit')
            if cint(custom_use_second_unit) == 1:
                if flt(i.custom_alternate_qty) <= 0.0:
                    frappe.throw("Fill the alternative quantity!")


    # on submit
    def zzzzon_submit(self):
        #super().on_submit()

        # Check for Approving Authority
        frappe.get_doc("Authorization Control").validate_approving_authority(
            self.doctype, self.company, self.base_grand_total
        )

        self.update_prevdoc_status()
        if flt(self.per_billed) < 100:
            self.update_billing_status()
        else:
            self.db_set("status", "Completed")

        self.make_bundle_using_old_serial_batch_fields()
        # Updating stock ledger should always be called after updating prevdoc status,
        # because updating ordered qty, reserved_qty_for_subcontract in bin
        # depends upon updated ordered qty in PO
        self.update_stock_ledger_2()
        self.make_gl_entries()
        self.repost_future_sle_and_gle()
        self.set_consumed_qty_in_subcontract_order()
        self.reserve_stock_for_sales_order()


    def update_stock_ledger_2(self, allow_negative_stock=False, via_landed_cost_voucher=False):
        self.update_ordered_and_reserved_qty()

        sl_entries = []
        stock_items = self.get_stock_items()

        for d in self.get("items"):
            if d.item_code not in stock_items:
                continue

            if d.warehouse:
                pr_qty = flt(flt(d.qty) * flt(d.conversion_factor), d.precision("stock_qty"))

                if pr_qty:
                    if d.from_warehouse and (
                        (not cint(self.is_return) and self.docstatus == 1)
                        or (cint(self.is_return) and self.docstatus == 2)
                    ):
                        serial_and_batch_bundle = d.get("serial_and_batch_bundle")
                        if self.is_internal_transfer() and self.is_return and self.docstatus == 2:
                            serial_and_batch_bundle = frappe.db.get_value(
                                "Stock Ledger Entry",
                                {"voucher_detail_no": d.name, "warehouse": d.from_warehouse},
                                "serial_and_batch_bundle",
                            )

                        from_warehouse_sle = self.get_sl_entries(
                            d,
                            {
                                "actual_qty": -1 * pr_qty,
                                "custom_alternate_qty": -1 * d.custom_alternate_qty,
                                "warehouse": d.from_warehouse,
                                "outgoing_rate": d.rate,
                                "recalculate_rate": 1,
                                "dependant_sle_voucher_detail_no": d.name,
                                "serial_and_batch_bundle": serial_and_batch_bundle,
                            },
                        )

                        sl_entries.append(from_warehouse_sle)

                    type_of_transaction = "Inward"
                    if self.docstatus == 2:
                        type_of_transaction = "Outward"

                    sle = self.get_sl_entries(
                        d,
                        {
                            "actual_qty": flt(pr_qty),
                            "custom_alternate_qty": flt(d.custom_alternate_qty),
                            "serial_and_batch_bundle": (
                                d.serial_and_batch_bundle
                                if not self.is_internal_transfer() or self.is_return
                                else self.get_package_for_target_warehouse(
                                    d, type_of_transaction=type_of_transaction
                                )
                            ),
                        },
                    )

                    if self.is_return:
                        outgoing_rate = get_rate_for_return(
                            self.doctype, self.name, d.item_code, self.return_against, item_row=d
                        )

                        sle.update(
                            {
                                "outgoing_rate": outgoing_rate,
                                "recalculate_rate": 1,
                                "serial_and_batch_bundle": d.serial_and_batch_bundle,
                            }
                        )
                        if d.from_warehouse:
                            sle.dependant_sle_voucher_detail_no = d.name
                    else:
                        val_rate_db_precision = 6 if cint(self.precision("valuation_rate", d)) <= 6 else 9
                        incoming_rate = flt(d.valuation_rate, val_rate_db_precision)
                        sle.update(
                            {
                                "incoming_rate": incoming_rate,
                                "recalculate_rate": 1
                                if (self.is_subcontracted and (d.bom or d.get("fg_item"))) or d.from_warehouse
                                else 0,
                            }
                        )
                    sl_entries.append(sle)

                    if d.from_warehouse and (
                        (not cint(self.is_return) and self.docstatus == 2)
                        or (cint(self.is_return) and self.docstatus == 1)
                    ):
                        from_warehouse_sle = self.get_sl_entries(
                            d,
                            {
                                "actual_qty": -1 * pr_qty,
                                "custom_alternate_qty": -1 * flt(d.custom_alternate_qty),
                                "warehouse": d.from_warehouse,
                                "recalculate_rate": 1,
                                "serial_and_batch_bundle": (
                                    self.get_package_for_target_warehouse(d, d.from_warehouse, "Inward")
                                    if self.is_internal_transfer() and self.is_return
                                    else None
                                ),
                            },
                        )

                        sl_entries.append(from_warehouse_sle)

            if flt(d.rejected_qty) != 0:
                sl_entries.append(
                    self.get_sl_entries(
                        d,
                        {
                            "warehouse": d.rejected_warehouse,
                            "actual_qty": flt(
                                flt(d.rejected_qty) * flt(d.conversion_factor), d.precision("stock_qty")
                            ),
                            "custom_alternate_qty": flt(d.custom_alternate_qty),
                            "incoming_rate": 0.0,
                            "serial_and_batch_bundle": d.rejected_serial_and_batch_bundle,
                        },
                    )
                )

        if self.get("is_old_subcontracting_flow"):
            self.make_sl_entries_for_supplier_warehouse(sl_entries)

        self.make_sl_entries(
            sl_entries,
            allow_negative_stock=allow_negative_stock,
            via_landed_cost_voucher=via_landed_cost_voucher,
        )