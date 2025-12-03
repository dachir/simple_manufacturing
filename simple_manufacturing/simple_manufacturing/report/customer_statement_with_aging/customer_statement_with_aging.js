frappe.query_reports["Customer Statement with Aging"] = {
    "filters": [

        {
            fieldname: "customer",
            label: __("Customer"),
            fieldtype: "Link",
            options: "Customer",
            reqd: 1,
            onchange: function (query_report) {
                let customer = frappe.query_report.get_filter_value("customer");
                if (customer) {
                    frappe.db.get_value("Customer", customer, "default_company")
                        .then(r => {
                            if (r && r.message && r.message.default_company) {
                                frappe.query_report.set_filter_value("company", r.message.default_company);
                            }
                        });
                }
            }
        },

        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company",
            reqd: 1
        },

        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -1)
        },

        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1
        },

        {
            fieldname: "show_ageing_split",
            label: __("Show Ageing Summary"),
            fieldtype: "Check",
            default: 1
        }
    ],

    // Hook after loading data
    onload: function(report) {
        // Add a refresh button
        report.page.add_inner_button(__("Refresh Statement"), function() {
            report.refresh();
        });
    },

    // Hook after report data loads
    after_datatable_render: function(report) {
        let show_split = frappe.query_report.get_filter_value("show_ageing_split");

        // Hide ageing summary row if not selected
        if (!show_split) {
            let rows = report.datatable.wrapper.getElementsByClassName("dt-row");
            if (rows && rows.length) {
                for (let i = rows.length - 1; i >= 0; i--) {
                    let cell = rows[i].innerText.toLowerCase();
                    if (cell.includes("aging summary") || cell.includes("ageing summary")) {
                        rows[i].style.display = "none";
                    }
                }
            }
        }
    }
};
