import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt, date_diff, in_words, getdate, add_days
from pdc_management.pdc_management.utils import get_pdc_clearing_account, get_party_account


class PDCCheque(Document):

    # ─────────────────────────────────────────
    # VALIDATE
    # ─────────────────────────────────────────
    def validate(self):
        self.validate_party_vs_type()
        self.validate_duplicate()
        self.set_party_account()
        self.set_amount_in_words()
        self.set_days_to_maturity()
        self.validate_allocated_amount()
        if self.docstatus == 0:
            self.status = "Draft"

    def validate_party_vs_type(self):
        if self.cheque_type == "Receivable" and self.party_type != "Customer":
            frappe.throw(_("Receivable PDC must have Party Type = Customer"))
        if self.cheque_type == "Payable" and self.party_type != "Supplier":
            frappe.throw(_("Payable PDC must have Party Type = Supplier"))

    def validate_duplicate(self):
        if not self.cheque_number or not self.party:
            return
        existing = frappe.db.exists("PDC Cheque", {
            "cheque_number": self.cheque_number,
            "bank_name": self.bank_name,
            "party": self.party,
            "name": ["!=", self.name],
            "docstatus": ["!=", 2],
            "status": ["not in", ["Cancelled", "Bounced"]]
        })
        if existing:
            frappe.throw(_(
                "Cheque number <b>{0}</b> from bank <b>{1}</b> is already "
                "registered for <b>{2}</b> as <a href='/app/pdc-cheque/{3}'>{3}</a>"
            ).format(self.cheque_number, self.bank_name, self.party, existing))

    def set_party_account(self):
        if self.party_type and self.party and self.company:
            try:
                self.party_account = get_party_account(
                    self.party_type, self.party, self.company)
            except Exception:
                pass

    def set_amount_in_words(self):
        if self.amount:
            self.amount_in_words = in_words(self.amount)

    def set_days_to_maturity(self):
        if self.cheque_date:
            self.days_to_maturity = date_diff(self.cheque_date, today())

    def validate_allocated_amount(self):
        if not self.references:
            return
        total_allocated = sum(flt(r.allocated_amount) for r in self.references)
        if total_allocated > flt(self.amount):
            frappe.throw(_(
                "Total Allocated Amount <b>{0}</b> cannot exceed "
                "Cheque Amount <b>{1}</b>"
            ).format(total_allocated, self.amount))

    # ─────────────────────────────────────────
    # ON SUBMIT
    # ─────────────────────────────────────────
    def on_submit(self):
        self.db_set("status", "Registered")
        self._log("Registered",
            "Cheque submitted and registered. No accounting entry created yet.")
        frappe.msgprint(
            _("PDC Cheque <b>{0}</b> Registered successfully. "
              "No GL impact until deposited.").format(self.name),
            indicator="blue", alert=True
        )

    # ─────────────────────────────────────────
    # ON CANCEL
    # ─────────────────────────────────────────
    def on_cancel(self):
        if self.status in ["Deposited", "Cleared"]:
            frappe.throw(_(
                "Cannot cancel a <b>{0}</b> cheque. "
                "Please mark it as Bounced first to reverse entries."
            ).format(self.status))
        self.db_set("status", "Cancelled")
        self._log("Cancelled", "PDC Cheque cancelled.")

    # ─────────────────────────────────────────
    # ACTION: DEPOSIT
    # ─────────────────────────────────────────
    @frappe.whitelist()
    def mark_as_deposited(self):
        if self.status != "Registered":
            frappe.throw(_("Only <b>Registered</b> cheques can be deposited."))

        clearing = get_pdc_clearing_account(
            self.company,
            "receivable" if self.cheque_type == "Receivable" else "payable"
        )
        party_acc = self.party_account or get_party_account(
            self.party_type, self.party, self.company)
        cost_center = (self.cost_center or
            frappe.db.get_value("Company", self.company, "cost_center"))

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.company = self.company
        je.posting_date = today()
        je.cheque_no = self.cheque_number
        je.cheque_date = self.cheque_date
        je.user_remark = (
            f"PDC Deposit — Cheque No: {self.cheque_number} | "
            f"Bank: {self.bank_name} | Party: {self.party} | "
            f"Amount: {self.amount} {self.currency}"
        )

        # Get references for JE
        ref_type = ""
        ref_name = ""
        if self.references and len(self.references) == 1:
            ref_type = self.references[0].reference_doctype
            ref_name = self.references[0].reference_document

        if self.cheque_type == "Receivable":
            # DR: PDC Clearing  CR: Customer AR
            je.append("accounts", {
                "account": clearing,
                "debit_in_account_currency": flt(self.amount),
                "credit_in_account_currency": 0,
                "cost_center": cost_center,
                "user_remark": f"PDC Clearing — {self.cheque_number}"
            })
            je.append("accounts", {
                "account": party_acc,
                "party_type": "Customer",
                "party": self.party,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": flt(self.amount),
                "reference_type": ref_type,
                "reference_name": ref_name,
                "user_remark": f"PDC Received — {self.cheque_number}"
            })
        else:
            # DR: Supplier AP  CR: PDC Clearing
            je.append("accounts", {
                "account": party_acc,
                "party_type": "Supplier",
                "party": self.party,
                "debit_in_account_currency": flt(self.amount),
                "credit_in_account_currency": 0,
                "reference_type": ref_type,
                "reference_name": ref_name,
                "user_remark": f"PDC Issued — {self.cheque_number}"
            })
            je.append("accounts", {
                "account": clearing,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": flt(self.amount),
                "cost_center": cost_center,
                "user_remark": f"PDC Clearing — {self.cheque_number}"
            })

        je.insert(ignore_permissions=True)
        je.submit()

        self.db_set("status", "Deposited")
        self.db_set("deposit_date", today())
        self.db_set("journal_entry", je.name)
        self._log("Deposited",
            f"Deposit Journal Entry {je.name} created. "
            f"Party account affected.")

        frappe.msgprint(
            _("✅ Cheque marked as <b>Deposited</b>. "
              "Journal Entry <b>{0}</b> created.").format(je.name),
            indicator="green", alert=True
        )
        return je.name

    # ─────────────────────────────────────────
    # ACTION: CLEAR
    # ─────────────────────────────────────────
    @frappe.whitelist()
    def mark_as_cleared(self):
        if self.status != "Deposited":
            frappe.throw(_("Only <b>Deposited</b> cheques can be cleared."))
        # Try to get default bank from PDC Settings
        if not self.bank_account:
            from pdc_management.pdc_management.utils import get_default_bank_account
            self.bank_account = get_default_bank_account(self.company)
        if not self.bank_account:
            frappe.throw(_(
                "Please set <b>Deposit To (Bank Account)</b> before clearing."
            ))

        clearing = get_pdc_clearing_account(
            self.company,
            "receivable" if self.cheque_type == "Receivable" else "payable"
        )

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Bank Entry"
        je.company = self.company
        je.posting_date = today()
        je.cheque_no = self.cheque_number
        je.cheque_date = self.cheque_date
        je.user_remark = (
            f"PDC Clearance — Cheque No: {self.cheque_number} | "
            f"Bank: {self.bank_name} | Party: {self.party}"
        )

        if self.cheque_type == "Receivable":
            # DR: Bank  CR: PDC Clearing
            je.append("accounts", {
                "account": self.bank_account,
                "debit_in_account_currency": flt(self.amount),
                "credit_in_account_currency": 0,
                "user_remark": f"PDC Cleared — Cheque {self.cheque_number}"
            })
            je.append("accounts", {
                "account": clearing,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": flt(self.amount),
                "user_remark": f"PDC Clearing Settled — {self.cheque_number}"
            })
        else:
            # DR: PDC Clearing  CR: Bank
            je.append("accounts", {
                "account": clearing,
                "debit_in_account_currency": flt(self.amount),
                "credit_in_account_currency": 0,
                "user_remark": f"PDC Clearing Settled — {self.cheque_number}"
            })
            je.append("accounts", {
                "account": self.bank_account,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": flt(self.amount),
                "user_remark": f"PDC Payment — Cheque {self.cheque_number}"
            })

        je.insert(ignore_permissions=True)
        je.submit()

        self.db_set("status", "Cleared")
        self.db_set("clearance_date", today())
        self.db_set("clearance_journal_entry", je.name)
        self._log("Cleared",
            f"Clearance Journal Entry {je.name} created. Cash in bank.")

        frappe.msgprint(
            _("✅ Cheque marked as <b>Cleared</b>. "
              "Journal Entry <b>{0}</b> created.").format(je.name),
            indicator="green", alert=True
        )
        return je.name

    # ─────────────────────────────────────────
    # ACTION: BOUNCE
    # ─────────────────────────────────────────
    @frappe.whitelist()
    def mark_as_bounced(self):
        if self.status not in ["Deposited", "Cleared"]:
            frappe.throw(_(
                "Only <b>Deposited</b> or <b>Cleared</b> cheques can be bounced."
            ))

        if self.journal_entry:
            orig = frappe.get_doc("Journal Entry", self.journal_entry)
            rev = frappe.new_doc("Journal Entry")
            rev.voucher_type = "Journal Entry"
            rev.company = self.company
            rev.posting_date = today()
            rev.user_remark = (
                f"PDC Bounce Reversal — Cheque: {self.cheque_number} | "
                f"Party: {self.party} | Reversal of JE: {self.journal_entry}"
            )
            for acc in orig.accounts:
                rev.append("accounts", {
                    "account": acc.account,
                    "party_type": acc.party_type,
                    "party": acc.party,
                    "debit_in_account_currency": acc.credit_in_account_currency,
                    "credit_in_account_currency": acc.debit_in_account_currency,
                    "reference_type": acc.reference_type,
                    "reference_name": acc.reference_name,
                    "cost_center": acc.cost_center,
                })
            rev.insert(ignore_permissions=True)
            rev.submit()
            self.db_set("bounce_journal_entry", rev.name)
            self.db_set("bounce_date", today())

        self.db_set("status", "Bounced")
        self._log("Bounced",
            f"Cheque bounced. All entries reversed. "
            f"Reversal JE: {self.bounce_journal_entry}")

        frappe.msgprint(
            _("⚠️ Cheque marked as <b>Bounced</b>. "
              "All accounting entries have been reversed."),
            indicator="red", alert=True
        )

    # ─────────────────────────────────────────
    # ACTION: RE-PRESENT (after bounce)
    # ─────────────────────────────────────────
    @frappe.whitelist()
    def mark_as_re_presented(self):
        """Re-present a bounced cheque — resets to Registered."""
        if self.status != "Bounced":
            frappe.throw(_("Only <b>Bounced</b> cheques can be re-presented."))
        self.db_set("status", "Registered")
        self.db_set("bounce_date", None)
        self.db_set("bounce_journal_entry", None)
        self._log("Registered",
            "Cheque re-presented after bounce. Reset to Registered.")
        frappe.msgprint(
            _("Cheque re-presented and reset to <b>Registered</b>."),
            indicator="blue", alert=True
        )

    # ─────────────────────────────────────────
    # HELPER: LOG
    # ─────────────────────────────────────────
    def _log(self, status, remarks):
        log = frappe.new_doc("PDC Cheque Log")
        log.pdc_cheque = self.name
        log.status = status
        log.date = today()
        log.remarks = remarks
        log.changed_by = frappe.session.user
        log.insert(ignore_permissions=True)


# ─────────────────────────────────────────────
# API — used by reports and dashboard
# ─────────────────────────────────────────────

@frappe.whitelist()
def get_pdc_summary(company=None):
    """Returns PDC summary counts and totals for dashboard."""
    filters = {"docstatus": 1}
    if company:
        filters["company"] = company

    data = frappe.get_all("PDC Cheque",
        filters=filters,
        fields=["cheque_type", "status", "amount", "currency"]
    )

    summary = {
        "receivable": {
            "registered": 0, "deposited": 0,
            "cleared": 0, "bounced": 0,
            "total_registered": 0, "total_deposited": 0,
            "total_cleared": 0, "total_bounced": 0
        },
        "payable": {
            "registered": 0, "deposited": 0,
            "cleared": 0, "bounced": 0,
            "total_registered": 0, "total_deposited": 0,
            "total_cleared": 0, "total_bounced": 0
        }
    }

    for d in data:
        key = "receivable" if d.cheque_type == "Receivable" else "payable"
        status = d.status.lower()
        if status in summary[key]:
            summary[key][status] += 1
            summary[key][f"total_{status}"] += flt(d.amount)

    return summary


@frappe.whitelist()
def get_maturing_cheques(days=7, company=None):
    """Returns cheques maturing in the next X days."""
    filters = {
        "status": "Registered",
        "docstatus": 1,
        "cheque_date": ["between", [today(), add_days(today(), int(days))]]
    }
    if company:
        filters["company"] = company
    return frappe.get_all("PDC Cheque",
        filters=filters,
        fields=["name", "party", "cheque_type", "cheque_number",
                "cheque_date", "amount", "currency", "bank_name", "status"],
        order_by="cheque_date asc"
    )


# ─────────────────────────────────────────────
# SCHEDULED TASK
# ─────────────────────────────────────────────

def auto_process_matured_cheques():
    """Runs daily — auto-deposits matured cheques."""
    cheques = frappe.get_all("PDC Cheque",
        filters={
            "status": "Registered",
            "cheque_date": ["<=", today()],
            "docstatus": 1
        },
        fields=["name"]
    )
    for c in cheques:
        try:
            frappe.get_doc("PDC Cheque", c["name"]).mark_as_deposited()
            frappe.db.commit()
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"PDC Auto-Deposit Failed: {c['name']}"
            )


def send_maturity_notifications():
    """Runs daily — sends email alerts for cheques maturing soon."""
    cheques = frappe.get_all("PDC Cheque",
        filters={
            "status": "Registered",
            "docstatus": 1,
            "notification_sent": 0,
            "notify_email": ["!=", ""]
        },
        fields=["name", "notify_email", "notify_days_before",
                "cheque_date", "cheque_number", "party",
                "amount", "currency", "cheque_type"]
    )
    for c in cheques:
        days_before = c.notify_days_before or 3
        notify_date = add_days(c.cheque_date, -days_before)
        if getdate(today()) >= getdate(notify_date):
            try:
                frappe.sendmail(
                    recipients=[c.notify_email],
                    subject=f"PDC Maturity Alert — Cheque {c.cheque_number}",
                    message=f"""
                        <h3>PDC Cheque Maturity Notification</h3>
                        <table border="1" cellpadding="5">
                            <tr><td><b>Cheque No</b></td><td>{c.cheque_number}</td></tr>
                            <tr><td><b>Party</b></td><td>{c.party}</td></tr>
                            <tr><td><b>Type</b></td><td>{c.cheque_type}</td></tr>
                            <tr><td><b>Maturity Date</b></td><td>{c.cheque_date}</td></tr>
                            <tr><td><b>Amount</b></td><td>{c.amount} {c.currency}</td></tr>
                        </table>
                        <p>This cheque is due for deposit in {days_before} days.</p>
                    """
                )
                frappe.db.set_value("PDC Cheque", c.name,
                    "notification_sent", 1)
                frappe.db.set_value("PDC Cheque", c.name,
                    "last_notification_date", today())
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"PDC Notification Failed: {c['name']}"
                )
