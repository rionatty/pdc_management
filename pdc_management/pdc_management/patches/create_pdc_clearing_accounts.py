import frappe


def execute():
    companies = frappe.get_all("Company", fields=["name", "abbr"])
    for c in companies:
        _make("PDC Receivable Clearing", "Receivable", "Asset", c["name"], c["abbr"])
        _make("PDC Payable Clearing", "Payable", "Liability", c["name"], c["abbr"])
    frappe.db.commit()
    print("✅ PDC clearing accounts created")


def _make(account_name, account_type, root_type, company, abbr):
    full = f"{account_name} - {abbr}"
    if frappe.db.exists("Account", full):
        print(f"⏭ Skipping existing: {full}")
        return
    parent_map = {"Asset": "Current Assets", "Liability": "Current Liabilities"}
    parent = frappe.db.get_value(
        "Account",
        {"account_name": parent_map[root_type], "company": company, "is_group": 1},
        "name"
    )
    if not parent:
        print(f"⚠ No parent for {company}, skipping {account_name}")
        return
    doc = frappe.new_doc("Account")
    doc.account_name = account_name
    doc.account_type = account_type
    doc.root_type = root_type
    doc.is_group = 0
    doc.company = company
    doc.parent_account = parent
    doc.insert(ignore_permissions=True)
    print(f"✅ Created: {full}")
