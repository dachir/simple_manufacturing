from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

import frappe
from frappe.utils import cint, flt
from erpnext.setup.doctype.company.company import update_company_current_month_sales
#from erpnext.accounts.doctype.pricing_rule.utils import (
#	update_coupon_code_count,
#)
from erpnext.stock.get_item_details import get_bin_details, get_conversion_factor

class CustomSalesInvoice(SalesInvoice):

    def before_save(self):
        if self.update_stock == 1:
            for i in self.items:
                custom_use_second_unit = frappe.db.get_value('Item', i.item_code, 'custom_use_second_unit')
                if cint(custom_use_second_unit) == 1:
                    if self.is_return == 0:
                        if flt(i.custom_alternate_qty) <= 0.0:
                            frappe.throw("Alternative quantity should be greater than 0!")
                    else:
                        if flt(i.custom_alternate_qty) >= 0.0:
                            frappe.throw("Alternative quantity should be lower than 0!")

    
    def zzzzon_submit(self):
        self.validate_pos_paid_amount()

        if not self.auto_repeat:
            frappe.get_doc("Authorization Control").validate_approving_authority(
                self.doctype, self.company, self.base_grand_total, self
            )

        self.check_prev_docstatus()

        if self.is_return and not self.update_billed_amount_in_sales_order:
            # NOTE status updating bypassed for is_return
            self.status_updater = []

        self.update_status_updater_args()
        self.update_prevdoc_status()

        self.update_billing_status_in_dn()
        self.clear_unallocated_mode_of_payments()

        # Updating stock ledger should always be called after updating prevdoc status,
        # because updating reserved qty in bin depends upon updated delivered qty in SO
        if self.update_stock == 1:
            for table_name in ["items", "packed_items"]:
                if not self.get(table_name):
                    continue

                self.make_bundle_using_old_serial_batch_fields(table_name)
            self.update_stock_ledger_2()

        # this sequence because outstanding may get -ve
        self.make_gl_entries()

        if self.update_stock == 1:
            self.repost_future_sle_and_gle()

        if not self.is_return:
            self.update_billing_status_for_zero_amount_refdoc("Delivery Note")
            self.update_billing_status_for_zero_amount_refdoc("Sales Order")
            self.check_credit_limit()

        if cint(self.is_pos) != 1 and not self.is_return:
            self.update_against_document_in_jv()

        self.update_time_sheet(self.name)

        if frappe.db.get_single_value("Selling Settings", "sales_update_frequency") == "Each Transaction":
            update_company_current_month_sales(self.company)
            self.update_project()
        update_linked_doc(self.doctype, self.name, self.inter_company_invoice_reference)

        #if self.coupon_code:
        #    update_coupon_code_count(self.coupon_code, "used")

        # create the loyalty point ledger entry if the customer is enrolled in any loyalty program
        if (
            not self.is_return
            and not self.is_consolidated
            and self.loyalty_program
            and not self.dont_create_loyalty_points
        ):
            self.make_loyalty_point_entry()
        elif self.is_return and self.return_against and not self.is_consolidated and self.loyalty_program:
            against_si_doc = frappe.get_doc("Sales Invoice", self.return_against)
            against_si_doc.delete_loyalty_point_entry()
            against_si_doc.make_loyalty_point_entry()
        if self.redeem_loyalty_points and not self.is_consolidated and self.loyalty_points:
            self.apply_loyalty_points()

        self.process_common_party_accounting()

    def update_stock_ledger_2(self):
        self.update_reserved_qty()

        sl_entries = []
        # Loop over items and packed items table
        for d in self.get_item_list_2():
            if frappe.get_cached_value("Item", d.item_code, "is_stock_item") == 1 and flt(d.qty):
                if flt(d.conversion_factor) == 0.0:
                    d.conversion_factor = (
                        get_conversion_factor(d.item_code, d.uom).get("conversion_factor") or 1.0
                    )

                # On cancellation or return entry submission, make stock ledger entry for
                # target warehouse first, to update serial no values properly

                if d.warehouse and (
                    (not cint(self.is_return) and self.docstatus == 1)
                    or (cint(self.is_return) and self.docstatus == 2)
                ):
                    sl_entries.append(self.get_sle_for_source_warehouse_2(d))

                if d.target_warehouse:
                    sl_entries.append(self.get_sle_for_target_warehouse(d))

                if d.warehouse and (
                    (not cint(self.is_return) and self.docstatus == 2)
                    or (cint(self.is_return) and self.docstatus == 1)
                ):
                    sl_entries.append(self.get_sle_for_source_warehouse_2(d))

        self.make_sl_entries(sl_entries)

    def get_item_list_2(self):
        il = []
        for d in self.get("items"):
            if self.has_product_bundle(d.item_code):
                for p in self.get("packed_items"):
                    if p.parent_detail_docname == d.name and p.parent_item == d.item_code:
                        # the packing details table's qty is already multiplied with parent's qty
                        il.append(
                            frappe._dict(
                                {
                                    "warehouse": p.warehouse or d.warehouse,
                                    "item_code": p.item_code,
                                    "qty": flt(p.qty),
                                    "serial_no": p.serial_no if self.docstatus == 2 else None,
                                    "batch_no": p.batch_no if self.docstatus == 2 else None,
                                    "uom": p.uom,
                                    "serial_and_batch_bundle": p.serial_and_batch_bundle
                                    or get_serial_and_batch_bundle(p, self),
                                    "name": d.name,
                                    "target_warehouse": p.target_warehouse,
                                    "company": self.company,
                                    "voucher_type": self.doctype,
                                    "allow_zero_valuation": d.allow_zero_valuation_rate,
                                    "sales_invoice_item": d.get("sales_invoice_item"),
                                    "dn_detail": d.get("dn_detail"),
                                    "incoming_rate": p.get("incoming_rate"),
                                    "item_row": p,
                                    "custom_alternate_qty": flt(d.custom_alternate_qty) if d.custom_alternate_qty else 0.0,
                                }
                            )
                        )
            else:
                il.append(
                    frappe._dict(
                        {
                            "warehouse": d.warehouse,
                            "item_code": d.item_code,
                            "qty": d.stock_qty,
                            "serial_no": d.serial_no if self.docstatus == 2 else None,
                            "batch_no": d.batch_no if self.docstatus == 2 else None,
                            "uom": d.uom,
                            "stock_uom": d.stock_uom,
                            "conversion_factor": d.conversion_factor,
                            "serial_and_batch_bundle": d.serial_and_batch_bundle,
                            "name": d.name,
                            "target_warehouse": d.target_warehouse,
                            "company": self.company,
                            "voucher_type": self.doctype,
                            "allow_zero_valuation": d.allow_zero_valuation_rate,
                            "sales_invoice_item": d.get("sales_invoice_item"),
                            "dn_detail": d.get("dn_detail"),
                            "incoming_rate": d.get("incoming_rate"),
                            "item_row": d,
                            "custom_alternate_qty": flt(d.custom_alternate_qty) if d.custom_alternate_qty else 0.0,
                        }
                    )
                )

        return il


    def get_sle_for_source_warehouse_2(self, item_row):
        serial_and_batch_bundle = item_row.serial_and_batch_bundle
        if serial_and_batch_bundle and self.is_internal_transfer() and self.is_return:
            if self.docstatus == 1:
                serial_and_batch_bundle = self.make_package_for_transfer(
                    serial_and_batch_bundle, item_row.warehouse, type_of_transaction="Inward"
                )
            else:
                serial_and_batch_bundle = frappe.db.get_value(
                    "Stock Ledger Entry",
                    {"voucher_detail_no": item_row.name, "warehouse": item_row.warehouse},
                    "serial_and_batch_bundle",
                )

        sle = self.get_sl_entries(
            item_row,
            {
                "actual_qty": -1 * flt(item_row.qty),
                "incoming_rate": item_row.incoming_rate,
                "recalculate_rate": cint(self.is_return),
                "serial_and_batch_bundle": serial_and_batch_bundle,
                "custom_alternate_qty": -1 * flt(item_row.custom_alternate_qty)
            },
        )
        if item_row.target_warehouse and not cint(self.is_return):
            sle.dependant_sle_voucher_detail_no = item_row.name

        return sle

    



def update_linked_doc(doctype, name, inter_company_reference):
    if doctype in ["Sales Invoice", "Purchase Invoice"]:
        ref_field = "inter_company_invoice_reference"
    else:
        ref_field = "inter_company_order_reference"

    if inter_company_reference:
        frappe.db.set_value(doctype, inter_company_reference, ref_field, name)