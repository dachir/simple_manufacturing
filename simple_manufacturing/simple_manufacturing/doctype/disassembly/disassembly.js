// Copyright (c) 2024, Kossivi Amouzou and contributors
// For license information, please see license.txt

frappe.ui.form.on("Disassembly", {
    warehouse_out(frm) {
        if (!frm.doc.warehouse_in){
            frm.set_value("warehouse_in",frm.doc.warehouse_out);
        }
 	},
     item_out(frm) {
        if (!frm.doc.item_in){
            frm.set_value("item_in",frm.doc.item_out);
        }
 	},
});
