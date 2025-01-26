# Copyright (c) 2024, Kossivi Amouzou and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Disassembly(Document):
	
	def before_save(self):
		n = len(str(self.no_pack))
		n = 10 ** n
		if len(self.packages) == 0 :
			for i in range(self.no_pack) :
				n = n + 1
				self.append('packages',{
						"pack": self.batch + str(n)[1:],
						"quantity": self.quantity / self.no_pack,
					}
				)


	def on_submit(self):
		des_details = []

		sbb_args = frappe._dict(
			{
				"doctype": "Serial and Batch Bundle",
				"item_code": self.item_out,
				"company": self.company,
				"warehouse": self.warehouse_out,
				"type_of_transaction": "Outward",
				"voucher_type": "Stock Entry",
				"entries":[{
					"batch_no" : self.batch,
					"qty" : self.quantity,
				}],
			}
		)
		sbb = frappe.get_doc(sbb_args)
		sbb.insert()


		details = frappe._dict({
			"branch": self.branch,
			"s_warehouse": self.warehouse_out,
			#"t_warehouse": d.salesman + " - " + abbr,
			"item_code": self.item_out, 
			"qty": self.quantity,
			"serial_and_batch_bundle": sbb.name,
			"doctype": "Stock Entry Detail",
		})
		des_details.append(details)

		for i in self.packages:			
			batch = frappe.get_doc({
					"doctype": "Batch",
					"batch_id": i.pack,
					"item": self.item_in,
					"origin": self.name,
				}
			)
			batch.insert()
			# Ajout des détails d'entrée de stock pour chaque nouveau batch
			details = frappe._dict({
				"branch": self.branch,
				#"s_warehouse": self.warehouse_out,
				"t_warehouse": self.warehouse_in,
				"item_code": self.item_in, 
				"qty": i.quantity,
				"batch_no": batch.name,
				"doctype": "Stock Entry Detail",
			})
			des_details.append(details)

		# Création et soumission de l'entrée de stock (Repack)
		args = frappe._dict(
			{
				"stock_entry_type": "Repack",
				"doctype": "Stock Entry",
				#"docstatus": 0,
				"custom_origin": self.name,
				"custom_auto_batch_and_serial_number": 0,
				"items":des_details,
			}
		)

		repack = frappe.get_doc(args)
		repack.insert()
		#sbb.voucher_no = repack.name
		#sbb.save()
		#sbb.submit()
		repack.submit()

