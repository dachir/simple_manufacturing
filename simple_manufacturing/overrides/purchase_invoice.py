from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice

import frappe
from frappe.utils import cint, flt
from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
    update_linked_doc,

)

class CustomPurchaseInvoice(PurchaseInvoice):

    def before_save(self):
        if self.update_stock == 1:
            for i in self.items:
                custom_use_second_unit = frappe.db.get_value('Item', i.item_code, 'custom_use_second_unit')
                if cint(custom_use_second_unit) == 1:
                    if flt(i.custom_alternate_qty) <= 0.0:
                        frappe.throw("Fill the alternative quantity!")

    def zzzzon_submit(self):
        #super().on_submit()

        self.check_prev_docstatus()

        if self.is_return and not self.update_billed_amount_in_purchase_order:
            # NOTE status updating bypassed for is_return
            self.status_updater = []

        self.update_status_updater_args()
        self.update_prevdoc_status()

        frappe.get_doc("Authorization Control").validate_approving_authority(
            self.doctype, self.company, self.base_grand_total
        )

        if not self.is_return:
            self.update_against_document_in_jv()
            self.update_billing_status_for_zero_amount_refdoc("Purchase Receipt")
            self.update_billing_status_for_zero_amount_refdoc("Purchase Order")

        self.update_billing_status_in_pr()

        # Updating stock ledger should always be called after updating prevdoc status,
        # because updating ordered qty in bin depends upon updated ordered qty in PO
        if self.update_stock == 1:
            self.make_bundle_using_old_serial_batch_fields()
            self.update_stock_ledger_2()

            if self.is_old_subcontracting_flow:
                self.set_consumed_qty_in_subcontract_order()

        # this sequence because outstanding may get -negative
        self.make_gl_entries()

        if self.update_stock == 1:
            self.repost_future_sle_and_gle()

        if frappe.db.get_single_value("Buying Settings", "project_update_frequency") == "Each Transaction":
            self.update_project()

        update_linked_doc(self.doctype, self.name, self.inter_company_invoice_reference)
        self.update_advance_tax_references()

        self.process_common_party_accounting()


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