app_name = "pdc_management"
app_title = "PDC Management"
app_publisher = "Your Name"
app_description = "Post Dated Cheque Management for ERPNext"
app_email = "your@email.com"
app_license = "MIT"
app_version = "1.0.0"

scheduler_events = {
    "daily": [
        "pdc_management.pdc_management.doctype.pdc_cheque.pdc_cheque.auto_process_matured_cheques",
        "pdc_management.pdc_management.doctype.pdc_cheque.pdc_cheque.send_maturity_notifications"
    ]
}

doctype_js = {
    "Customer": "public/js/customer_pdc.js",
    "Supplier": "public/js/supplier_pdc.js",
}
