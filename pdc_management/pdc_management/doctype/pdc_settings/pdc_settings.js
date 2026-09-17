frappe.ui.form.on("PDC Settings", {

    refresh(frm) {
        frm.trigger("add_setup_button");
        frm.trigger("show_missing_companies");
    },

    // ── Button to auto-create clearing accounts ───────────────────────────
    add_setup_button(frm) {
        frm.add_custom_button(__("⚙️ Auto Setup Clearing Accounts"), () => {
            frappe.confirm(
                "This will automatically create <b>PDC Receivable Clearing</b> and " +
                "<b>PDC Payable Clearing</b> accounts for all companies and " +
                "populate this settings table. Continue?",
                () => {
                    frappe.call({
                        method: "pdc_management.pdc_management.doctype.pdc_settings.pdc_settings.auto_setup_accounts",
                        callback(r) {
                            if (r.message) {
                                frappe.msgprint({
                                    title: "Setup Complete",
                                    message: r.message,
                                    indicator: "green"
                                });
                                frm.reload_doc();
                            }
                        }
                    });
                }
            );
        }).css({ "background": "#2563eb", "color": "white", "font-weight": "bold" });
    },

    // ── Show which companies are missing settings ─────────────────────────
    show_missing_companies(frm) {
        frappe.call({
            method: "frappe.client.get_list",
            args: { doctype: "Company", fields: ["name"], limit: 100 },
            callback(r) {
                if (!r.message) return;
                const configured = (frm.doc.company_settings || []).map(r => r.company);
                const missing = r.message
                    .map(c => c.name)
                    .filter(c => !configured.includes(c));
                if (missing.length > 0) {
                    frm.dashboard.add_comment(
                        `⚠️ The following companies have no PDC settings: <b>${missing.join(", ")}</b>. 
                         Click <b>Auto Setup</b> to configure them automatically.`,
                        "orange", true
                    );
                } else {
                    frm.dashboard.add_comment(
                        "✅ All companies are configured with PDC clearing accounts.",
                        "green", true
                    );
                }
            }
        });
    }
});

// ── Child table: filter accounts by company ───────────────────────────────
frappe.ui.form.on("PDC Company Settings", {

    company(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.company) return;

        // Set filters for account fields based on selected company
        frm.fields_dict.company_settings.grid.update_docfield_property(
            "pdc_receivable_account", "get_query", () => ({
                filters: {
                    company: row.company,
                    is_group: 0,
                    root_type: "Asset"
                }
            })
        );
        frm.fields_dict.company_settings.grid.update_docfield_property(
            "pdc_payable_account", "get_query", () => ({
                filters: {
                    company: row.company,
                    is_group: 0,
                    root_type: "Liability"
                }
            })
        );
        frm.fields_dict.company_settings.grid.update_docfield_property(
            "default_bank_account", "get_query", () => ({
                filters: {
                    company: row.company,
                    is_group: 0,
                    account_type: "Bank"
                }
            })
        );
    }
});
