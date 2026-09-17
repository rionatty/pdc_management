import frappe
from frappe import _


def get_pdc_settings_for_company(company):
    """
    Returns the PDC Settings row for a given company.
    Raises a clear error if not configured.
    """
    try:
        settings = frappe.get_single("PDC Settings")
    except Exception:
        frappe.throw(
            _("PDC Settings not found. Please go to <b>PDC Settings</b> "
              "and configure your clearing accounts.")
        )

    for row in settings.company_settings:
        if row.company == company:
            return row

    frappe.throw(
        _("PDC Settings not configured for company <b>{0}</b>.<br>"
          "Please go to <b>PDC Settings</b> → Add a row for this company "
          "or click <b>Auto Setup Clearing Accounts</b>.").format(company)
    )


def get_pdc_clearing_account(company, pdc_type):
    """
    Returns the PDC clearing account for a company from PDC Settings.
    pdc_type: 'receivable' or 'payable'
    """
    row = get_pdc_settings_for_company(company)

    if pdc_type == "receivable":
        account = row.pdc_receivable_account
        label = "PDC Receivable Clearing Account"
    else:
        account = row.pdc_payable_account
        label = "PDC Payable Clearing Account"

    if not account:
        frappe.throw(
            _("<b>{0}</b> is not set for company <b>{1}</b>.<br>"
              "Please go to <b>PDC Settings</b> and configure it.").format(
                label, company)
        )
    return account


def get_default_bank_account(company):
    """
    Returns the default bank account for a company from PDC Settings.
    Falls back to ERPNext default if not set.
    """
    try:
        row = get_pdc_settings_for_company(company)
        if row.default_bank_account:
            return row.default_bank_account
    except Exception:
        pass

    # Fallback to company default
    return frappe.db.get_value(
        "Account",
        {"account_type": "Bank", "company": company, "is_group": 0},
        "name"
    )


def get_party_account(party_type, party, company):
    """Returns the AR/AP account for a customer/supplier."""
    from erpnext.accounts.party import get_party_account as _get
    return _get(party_type, party, company)


def get_pdc_auto_deposit_enabled():
    """Returns True if auto deposit on maturity is enabled in PDC Settings."""
    try:
        return frappe.db.get_single_value("PDC Settings", "auto_deposit_on_maturity")
    except Exception:
        return False


def get_pdc_notify_days():
    """Returns the number of days before maturity to send notification."""
    try:
        return frappe.db.get_single_value("PDC Settings", "notify_before_days") or 3
    except Exception:
        return 3
