frappe.ui.form.on("PDC Cheque", {

    // ── SETUP ──────────────────────────────────────────────────────────────
    setup(frm) {
        frm.set_query("bank_account", () => ({
            filters: {
                account_type: "Bank",
                company: frm.doc.company,
                is_group: 0
            }
        }));
        frm.set_query("cost_center", () => ({
            filters: {
                company: frm.doc.company,
                is_group: 0
            }
        }));
        frm.set_query("reference_document", "references", function(doc, cdt, cdn) {
            const row = locals[cdt][cdn];
            if (!row.reference_doctype || !frm.doc.party) return {};
            const filters = [
                [row.reference_doctype, "outstanding_amount", ">", 0],
                [row.reference_doctype, "docstatus", "=", 1]
            ];
            if (row.reference_doctype === "Sales Invoice") {
                filters.push([row.reference_doctype, "customer", "=", frm.doc.party]);
            } else if (row.reference_doctype === "Purchase Invoice") {
                filters.push([row.reference_doctype, "supplier", "=", frm.doc.party]);
            }
            return { filters };
        });
    },

    // ── ON REFRESH ─────────────────────────────────────────────────────────
    refresh(frm) {
        frm.trigger("set_party_type");
        frm.trigger("render_status_badge");
        frm.trigger("render_party_dashboard");
        frm.trigger("add_action_buttons");
        frm.trigger("set_fields_read_only");
        frm.trigger("show_maturity_alert");
        frm.trigger("update_allocation_totals");

        // "Get Outstanding Invoices" button — only on draft forms with a party selected
        if (frm.doc.docstatus === 0 && frm.doc.party && frm.doc.company) {
            frm.add_custom_button(__("Get Outstanding Invoices"), () => {
                frm.trigger("fetch_outstanding_invoices");
            });
        }
    },

    // ── FETCH OUTSTANDING INVOICES ─────────────────────────────────────────
    fetch_outstanding_invoices(frm) {
        if (!frm.doc.party || !frm.doc.company || !frm.doc.party_type) {
            frappe.msgprint(__("Please select Party and Company first."));
            return;
        }
        frappe.show_alert({ message: __("Fetching outstanding invoices…"), indicator: "blue" });
        frappe.call({
            method: "pdc_management.pdc_management.doctype.pdc_cheque.pdc_cheque.get_outstanding_invoices_for_party",
            args: {
                party_type: frm.doc.party_type,
                party: frm.doc.party,
                company: frm.doc.company,
                currency: frm.doc.currency || null
            },
            callback(r) {
                if (!r.message) return;
                const { invoices, total_outstanding } = r.message;

                if (!invoices.length) {
                    frappe.msgprint(__("No outstanding invoices found for this party."));
                    return;
                }

                frm.clear_table("references");
                invoices.forEach(inv => {
                    const row = frm.add_child("references");
                    row.reference_doctype  = inv.reference_doctype;
                    row.reference_document = inv.reference_document;
                    row.outstanding_amount = inv.outstanding_amount;
                    row.allocated_amount   = 0;
                    row.due_date           = inv.due_date;
                });
                frm.refresh_field("references");
                frm.set_value("total_outstanding", total_outstanding);
                if (flt(frm.doc.amount) > 0) {
                    frm.trigger("auto_allocate");
                } else {
                    frm.trigger("update_allocation_totals");
                }
                frappe.show_alert({
                    message: __(`${invoices.length} invoice(s) loaded.`),
                    indicator: "green"
                });
            }
        });
    },

    // ── ALLOCATION TOTALS ──────────────────────────────────────────────────
    update_allocation_totals(frm) {
        let total_allocated = 0;
        (frm.doc.references || []).forEach(r => {
            total_allocated += flt(r.allocated_amount);
        });
        frm.set_value("total_allocated", total_allocated);
        frm.set_value("unallocated_amount", flt(frm.doc.amount) - total_allocated);
    },

    amount(frm) {
        if (frm.doc.references && frm.doc.references.length) {
            frm.trigger("auto_allocate");
        } else {
            frm.trigger("update_allocation_totals");
        }
    },

    // ── AUTO ALLOCATE ──────────────────────────────────────────────────────
    // Distributes cheque amount across references oldest-first (like Payment Entry)
    auto_allocate(frm) {
        let remaining = flt(frm.doc.amount);
        (frm.doc.references || []).forEach(row => {
            const can_allocate = Math.min(remaining, flt(row.outstanding_amount));
            frappe.model.set_value(row.doctype, row.name, "allocated_amount", can_allocate);
            remaining = Math.max(0, remaining - can_allocate);
        });
        frm.refresh_field("references");
        frm.trigger("update_allocation_totals");
    },

    // ── STATUS BADGE ───────────────────────────────────────────────────────
    render_status_badge(frm) {
        const colorMap = {
            "Draft":      { bg: "#f0f0f0", color: "#666666", icon: "⬜" },
            "Registered": { bg: "#dbeafe", color: "#1d4ed8", icon: "📋" },
            "Deposited":  { bg: "#fef3c7", color: "#d97706", icon: "🏦" },
            "Cleared":    { bg: "#d1fae5", color: "#065f46", icon: "✅" },
            "Bounced":    { bg: "#fee2e2", color: "#991b1b", icon: "❌" },
            "Cancelled":  { bg: "#f3f4f6", color: "#6b7280", icon: "🚫" }
        };
        const s = colorMap[frm.doc.status] || colorMap["Draft"];
        frm.get_field("status_html").$wrapper.html(`
            <div style="margin-bottom:12px;">
                <span style="
                    display:inline-block;
                    background:${s.bg};
                    color:${s.color};
                    padding:6px 20px;
                    border-radius:20px;
                    font-size:14px;
                    font-weight:bold;
                    border:1px solid ${s.color}55;
                ">
                    ${s.icon} &nbsp; ${frm.doc.status || "Draft"}
                </span>
                ${frm.doc.days_to_maturity !== undefined && frm.doc.status === "Registered"
                    ? `<span style="
                        display:inline-block;
                        margin-left:10px;
                        background:#f3f4f6;
                        color:#374151;
                        padding:6px 14px;
                        border-radius:20px;
                        font-size:13px;
                        border:1px solid #d1d5db;
                      ">
                        📅 ${frm.doc.days_to_maturity >= 0
                            ? `Matures in <b>${frm.doc.days_to_maturity}</b> day(s)`
                            : `<span style="color:red">Overdue by <b>${Math.abs(frm.doc.days_to_maturity)}</b> day(s)</span>`
                        }
                      </span>`
                    : ""
                }
            </div>
        `);
    },

    // ── MATURITY ALERT BANNER ──────────────────────────────────────────────
    show_maturity_alert(frm) {
        if (!frm.doc.cheque_date || frm.doc.status !== "Registered") return;
        let days = frappe.datetime.get_diff(
            frm.doc.cheque_date, frappe.datetime.get_today()
        );
        if (days >= 0 && days <= 7) {
            frm.dashboard.add_comment(
                `⚠️ This cheque matures in <b>${days}</b> day(s) on <b>${frm.doc.cheque_date}</b>. Please prepare for deposit.`,
                "orange", true
            );
        } else if (days < 0) {
            frm.dashboard.add_comment(
                `🔴 This cheque <b>matured ${Math.abs(days)} day(s) ago</b> and has NOT been deposited yet!`,
                "red", true
            );
        }
    },

    // ── PARTY DASHBOARD ────────────────────────────────────────────────────
    render_party_dashboard(frm) {
        if (!frm.doc.party || frm.is_new()) return;

        frappe.call({
            method: "frappe.client.get_list",
            args: {
                doctype: "PDC Cheque",
                filters: {
                    party: frm.doc.party,
                    cheque_type: frm.doc.cheque_type,
                    docstatus: 1
                },
                fields: ["status", "amount"],
                limit: 500
            },
            callback(r) {
                if (!r.message) return;
                let totals = {
                    Registered: 0, Deposited: 0,
                    Cleared: 0, Bounced: 0
                };
                r.message.forEach(d => {
                    if (totals[d.status] !== undefined) {
                        totals[d.status] += flt(d.amount);
                    }
                });

                const card = (label, value, bg, color) => `
                    <div style="
                        flex:1; min-width:120px;
                        background:${bg}; border-radius:8px;
                        padding:12px; text-align:center;
                        border:1px solid ${color}33;
                    ">
                        <div style="font-size:10px;font-weight:bold;
                            color:${color};letter-spacing:0.5px;">
                            ${label}
                        </div>
                        <div style="font-size:15px;font-weight:bold;
                            color:${color};margin-top:4px;">
                            ${frappe.format(value, {fieldtype:"Currency"})}
                        </div>
                    </div>`;

                const html = `
                    <div style="
                        display:flex; gap:10px; flex-wrap:wrap;
                        margin:10px 0 14px 0; padding:10px;
                        background:#f9fafb; border-radius:10px;
                        border:1px solid #e5e7eb;
                    ">
                        <div style="width:100%;font-size:11px;
                            color:#6b7280;margin-bottom:4px;">
                            📊 PDC Summary for <b>${frm.doc.party}</b>
                        </div>
                        ${card("REGISTERED", totals.Registered, "#dbeafe", "#1d4ed8")}
                        ${card("DEPOSITED",  totals.Deposited,  "#fef3c7", "#d97706")}
                        ${card("CLEARED",    totals.Cleared,    "#d1fae5", "#065f46")}
                        ${card("BOUNCED",    totals.Bounced,    "#fee2e2", "#991b1b")}
                    </div>`;

                const wrapper = frm.get_field("status_html").$wrapper;
                wrapper.find(".pdc-dashboard").remove();
                wrapper.append(`<div class="pdc-dashboard">${html}</div>`);
            }
        });
    },

    // ── ACTION BUTTONS ─────────────────────────────────────────────────────
    add_action_buttons(frm) {
        if (frm.doc.docstatus !== 1) return;

        if (frm.doc.status === "Registered") {
            frm.add_custom_button(__("🏦 Deposit Cheque"), () => {
                frappe.confirm(
                    `<table style="width:100%;border-collapse:collapse;">
                        <tr><td style="padding:4px;color:#6b7280;">Cheque No</td>
                            <td style="padding:4px;font-weight:bold;">${frm.doc.cheque_number}</td></tr>
                        <tr><td style="padding:4px;color:#6b7280;">Party</td>
                            <td style="padding:4px;font-weight:bold;">${frm.doc.party}</td></tr>
                        <tr><td style="padding:4px;color:#6b7280;">Amount</td>
                            <td style="padding:4px;font-weight:bold;">
                                ${frappe.format(frm.doc.amount, {fieldtype:"Currency"})}
                            </td></tr>
                        <tr><td style="padding:4px;color:#6b7280;">Cheque Date</td>
                            <td style="padding:4px;font-weight:bold;">${frm.doc.cheque_date}</td></tr>
                    </table>
                    <br><b>This will create a Journal Entry and mark the cheque as Deposited.</b>`,
                    () => {
                        frappe.show_alert({ message: "Creating Journal Entry...", indicator: "blue" });
                        frm.call("mark_as_deposited").then(() => frm.reload_doc());
                    }
                );
            }, __("PDC Actions")).css({ "background": "#2563eb", "color": "white", "font-weight": "bold" });
        }

        if (frm.doc.status === "Deposited") {
            frm.add_custom_button(__("✅ Clear Cheque"), () => {
                if (!frm.doc.bank_account) {
                    frappe.msgprint({
                        title: "Bank Account Required",
                        message: "Please set the <b>Deposit To (Bank Account)</b> field before clearing.",
                        indicator: "red"
                    });
                    return;
                }
                frappe.confirm(
                    `Transfer <b>${frappe.format(frm.doc.amount, {fieldtype:"Currency"})}</b>
                     from <b>PDC Clearing</b> to <b>${frm.doc.bank_account}</b>?`,
                    () => {
                        frappe.show_alert({ message: "Processing clearance...", indicator: "green" });
                        frm.call("mark_as_cleared").then(() => frm.reload_doc());
                    }
                );
            }, __("PDC Actions")).css({ "background": "#059669", "color": "white", "font-weight": "bold" });

            frm.add_custom_button(__("❌ Mark as Bounced"), () => {
                frappe.confirm(
                    `<span style="color:red;font-weight:bold;">⚠️ WARNING</span><br><br>
                     Marking cheque <b>${frm.doc.cheque_number}</b> as bounced will
                     <b>REVERSE all Journal Entries</b> and restore the
                     outstanding balance to <b>${frm.doc.party}</b>.<br><br>
                     Are you sure you want to continue?`,
                    () => {
                        frappe.show_alert({ message: "Reversing entries...", indicator: "red" });
                        frm.call("mark_as_bounced").then(() => frm.reload_doc());
                    }
                );
            }, __("PDC Actions")).css({ "background": "#dc2626", "color": "white", "font-weight": "bold" });
        }

        if (frm.doc.status === "Bounced") {
            frm.add_custom_button(__("🔄 Re-Present Cheque"), () => {
                frappe.confirm(
                    `Re-present cheque <b>${frm.doc.cheque_number}</b>?
                     It will be reset to <b>Registered</b> status.`,
                    () => frm.call("mark_as_re_presented").then(() => frm.reload_doc())
                );
            }, __("PDC Actions")).css({ "background": "#7c3aed", "color": "white", "font-weight": "bold" });
        }

        if (frm.doc.journal_entry) {
            frm.add_custom_button(__("📄 Deposit JE"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry);
            }, __("View"));
        }
        if (frm.doc.clearance_journal_entry) {
            frm.add_custom_button(__("📄 Clearance JE"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.clearance_journal_entry);
            }, __("View"));
        }
        if (frm.doc.bounce_journal_entry) {
            frm.add_custom_button(__("📄 Bounce JE"), () => {
                frappe.set_route("Form", "Journal Entry", frm.doc.bounce_journal_entry);
            }, __("View"));
        }
        frm.add_custom_button(__("📋 All PDCs for Party"), () => {
            frappe.set_route("List", "PDC Cheque", { party: frm.doc.party });
        }, __("View"));
    },

    // ── AUTO SET PARTY TYPE ────────────────────────────────────────────────
    set_party_type(frm) {
        if (frm.doc.cheque_type === "Receivable") {
            frm.set_value("party_type", "Customer");
        } else if (frm.doc.cheque_type === "Payable") {
            frm.set_value("party_type", "Supplier");
        }
    },

    cheque_type(frm) {
        frm.trigger("set_party_type");
        frm.set_value("party", "");
        frm.set_value("party_account", "");
        frm.set_value("party_name", "");
        frm.set_value("total_outstanding", 0);
    },

    // ── DAYS TO MATURITY ───────────────────────────────────────────────────
    cheque_date(frm) {
        if (frm.doc.cheque_date) {
            let days = frappe.datetime.get_diff(
                frm.doc.cheque_date,
                frappe.datetime.get_today()
            );
            frm.set_value("days_to_maturity", days);
            frm.trigger("show_maturity_alert");
        }
    },

    // ── PARTY SELECTED ─────────────────────────────────────────────────────
    party(frm) {
        if (!frm.doc.party || !frm.doc.party_type || !frm.doc.company) {
            frm.set_value("party_name", "");
            frm.set_value("total_outstanding", 0);
            return;
        }

        // Fetch party display name (works for both Customer and Supplier)
        const nameField = frm.doc.party_type === "Customer" ? "customer_name" : "supplier_name";
        frappe.db.get_value(frm.doc.party_type, frm.doc.party, nameField, r => {
            frm.set_value("party_name", r && r[nameField] || "");
        });

        // Fetch party ledger account
        frappe.call({
            method: "erpnext.accounts.party.get_party_account",
            args: {
                party_type: frm.doc.party_type,
                party: frm.doc.party,
                company: frm.doc.company
            },
            callback(r) {
                if (r.message) frm.set_value("party_account", r.message);
            }
        });

        // Auto-fetch outstanding invoices and populate references table
        frappe.show_alert({ message: __("Loading outstanding invoices…"), indicator: "blue" });
        frappe.call({
            method: "pdc_management.pdc_management.doctype.pdc_cheque.pdc_cheque.get_outstanding_invoices_for_party",
            args: {
                party_type: frm.doc.party_type,
                party: frm.doc.party,
                company: frm.doc.company,
                currency: frm.doc.currency || null
            },
            callback(r) {
                if (!r.message) return;
                const { invoices, total_outstanding } = r.message;

                frm.set_value("total_outstanding", total_outstanding);

                // Populate references table
                frm.clear_table("references");
                invoices.forEach(inv => {
                    const row = frm.add_child("references");
                    row.reference_doctype  = inv.reference_doctype;
                    row.reference_document = inv.reference_document;
                    row.outstanding_amount = inv.outstanding_amount;
                    row.allocated_amount   = 0;  // will be set by auto-allocate
                    row.due_date           = inv.due_date;
                });
                frm.refresh_field("references");

                // Auto-allocate if amount is already filled
                if (flt(frm.doc.amount) > 0) {
                    frm.trigger("auto_allocate");
                } else {
                    frm.trigger("update_allocation_totals");
                }
            }
        });

        frm.trigger("render_party_dashboard");
    },

    // ── AUTO SET COST CENTER ───────────────────────────────────────────────
    company(frm) {
        if (frm.doc.company) {
            frappe.db.get_value("Company", frm.doc.company, "cost_center", r => {
                if (r && r.cost_center) frm.set_value("cost_center", r.cost_center);
            });
        }
    },

    // ── LOCK FIELDS AFTER SUBMIT ───────────────────────────────────────────
    set_fields_read_only(frm) {
        if (frm.doc.docstatus === 1) {
            [
                "cheque_type", "party_type", "party",
                "cheque_number", "cheque_date", "amount",
                "currency", "bank_name", "receipt_date"
            ].forEach(f => frm.set_df_property(f, "read_only", 1));
        }
    }
});

// ── CHILD TABLE: fetch outstanding on invoice select ──────────────────────
frappe.ui.form.on("PDC Cheque Invoice", {
    reference_document(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.reference_document || !row.reference_doctype) return;
        frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: row.reference_doctype,
                fieldname: ["outstanding_amount", "due_date"],
                filters: { name: row.reference_document }
            },
            callback(r) {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, "outstanding_amount",
                        r.message.outstanding_amount);
                    frappe.model.set_value(cdt, cdn, "allocated_amount",
                        r.message.outstanding_amount);
                    if (r.message.due_date) {
                        frappe.model.set_value(cdt, cdn, "due_date", r.message.due_date);
                    }
                }
            }
        });
    },

    allocated_amount(frm) {
        frm.trigger("update_allocation_totals");
    },

    references_remove(frm) {
        frm.trigger("update_allocation_totals");
    }
});

function flt(val) {
    return parseFloat(val) || 0;
}
