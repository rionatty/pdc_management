import frappe
from frappe import _
from frappe.model.document import Document


class PDCSettings(Document):

    def validate(self):
        self.validate_no_duplicate_company()
        self.validate_accounts()

    def validate_no_duplicate_company(self):
        """Ensure each company appears only once in the settings table."""
        companies = [row.company for row in self.company_settings]
        duplicates = [c for c in companies if companies.count(c) > 1]
        if duplicates:
            frappe.throw(
                _("Company <b>{0}</b> appears more than once in Company Settings. "
                  "Each company must have only one configuration.").format(duplicates[0])
            )

    def validate_accounts(self):
        """Ensure clearing accounts belong to correct company."""
        for row in self.company_settings:
            if row.pdc_receivable_account:
                acc_company = frappe.db.get_value(
                    "Account", row.pdc_receivable_account, "company")
                if acc_company != row.company:
                    frappe.throw(
                        _("Row {0}: PDC Receivable Account <b>{1}</b> does not "
                          "belong to company <b>{2}</b>").format(
                            row.idx, row.pdc_receivable_account, row.company)
                    )
            if row.pdc_payable_account:
                acc_company = frappe.db.get_value(
                    "Account", row.pdc_payable_account, "company")
                if acc_company != row.company:
                    frappe.throw(
                        _("Row {0}: PDC Payable Account <b>{1}</b> does not "
                          "belong to company <b>{2}</b>").format(
                            row.idx, row.pdc_payable_account, row.company)
                    )


@frappe.whitelist()
def auto_setup_accounts():
    """
    Automatically creates PDC clearing accounts for all companies
    and populates the PDC Settings table.
    """
    companies = frappe.get_all("Company", fields=["name", "abbr"])
    results = []
    settings = frappe.get_single("PDC Settings")
    existing_companies = [r.company for r in settings.company_settings]

    for company in companies:
        rec_account = _ensure_account(
            "PDC Receivable Clearing", "Receivable",
            "Asset", "Current Assets",
            company["name"], company["abbr"]
        )
        pay_account = _ensure_account(
            "PDC Payable Clearing", "Payable",
            "Liability", "Current Liabilities",
            company["name"], company["abbr"]
        )

        if company["name"] not in existing_companies:
            settings.append("company_settings", {
                "company": company["name"],
                "pdc_receivable_account": rec_account,
                "pdc_payable_account": pay_account
            })
            results.append(f"✅ Configured: {company['name']}")
        else:
            results.append(f"⏭ Already configured: {company['name']}")

    settings.save(ignore_permissions=True)
    frappe.db.commit()
    return "<br>".join(results)


def _ensure_account(account_name, account_type, root_type,
                    parent_account_name, company, abbr):
    """Create account if it doesn't exist, return its name."""
    full_name = f"{account_name} - {abbr}"
    if frappe.db.exists("Account", full_name):
        return full_name

    parent = frappe.db.get_value(
        "Account",
        {
            "account_name": parent_account_name,
            "company": company,
            "is_group": 1
        },
        "name"
    )
    if not parent:
        frappe.log_error(
            f"Parent account '{parent_account_name}' not found for {company}",
            "PDC Auto Setup"
        )
        return None

    doc = frappe.new_doc("Account")
    doc.account_name = account_name
    doc.account_type = account_type
    doc.root_type = root_type
    doc.is_group = 0
    doc.company = company
    doc.parent_account = parent
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return full_name
