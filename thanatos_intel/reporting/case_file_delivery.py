"""Consegna file del caso: (1) organizza nella cartella Drive corretta del caso;
(2) se self_mode (acquisto self-serve del cliente) pubblica nel portale del cliente
(Client Vault Item → /portal/vault, con copia file accessibile al cliente) e invia
email con il link.

Additivo e riusabile: vale per export openapi, documenti ufficiali, fascicolo/dossier.
"""
import frappe


def _is_real_email(e):
    e = (e or "").strip().lower()
    return bool(e) and "@" in e and "@lead." not in e and "@daidentificare" not in e


@frappe.whitelist()
def deliver_case_file(case, file_url, file_name=None, doc_kind="Altro", self_mode=0, notify_email=1):
    self_mode = int(self_mode or 0)
    c = frappe.db.get_value("Investigation Case", case,
                            ["client", "drive_folder", "case_title"], as_dict=True)
    if not c:
        frappe.throw("Caso non trovato")
    title = (file_name or c.case_title or case)[:140]
    out = {"case": case, "file": file_url, "title": title}

    # 1) cartella corretta (Drive del caso) — best effort
    if c.drive_folder:
        try:
            from thanatos_intel.reporting.case_reports import organize_case_files_to_drive
            organize_case_files_to_drive(case)
            out["drive"] = True
        except Exception:
            frappe.log_error(frappe.get_traceback(), "deliver_case_file drive")

    # 2) self mode → portale cliente + email
    if self_mode and c.client:
        if not frappe.db.exists("Client Vault Item", {"client": c.client, "title": title}):
            vi = frappe.get_doc({"doctype": "Client Vault Item", "client": c.client,
                                 "doc_kind": doc_kind, "title": title, "status": "Valido"})
            vi.insert(ignore_permissions=True)
            vault_url = file_url
            # copia il file allegandolo al Vault Item (accessibile al cliente); campo via SQL (no validazione Attach)
            try:
                from frappe.utils.file_manager import get_file, save_file
                fname, content = get_file(file_url)
                f2 = save_file(fname, content, "Client Vault Item", vi.name, is_private=1)
                vault_url = f2.file_url
            except Exception:
                frappe.log_error(frappe.get_traceback(), "deliver_case_file copy")
            frappe.db.sql("update `tabClient Vault Item` set file=%s where name=%s", (vault_url, vi.name))
            out["portal"] = True
        else:
            out["portal"] = "exists"
        if int(notify_email or 0):
            to = frappe.db.get_value("Investigation Client", c.client, "email")
            if _is_real_email(to):
                try:
                    base = frappe.utils.get_url()
                    frappe.sendmail(
                        recipients=[to],
                        subject="Documento disponibile — %s" % title,
                        message=("<p>Gentile cliente,</p>"
                                 "<p>il documento <b>%s</b> richiesto è pronto.</p>"
                                 "<p>Lo trovi nel tuo <a href='%s/portal/vault'>Archivio documenti</a>.</p>"
                                 % (frappe.utils.escape_html(title), base)))
                    out["email"] = {"ok": True, "to": to}
                except Exception as e:
                    out["email"] = {"ok": False, "error": str(e)[:160]}
            else:
                out["email"] = {"ok": False, "error": "email cliente non valida"}
    frappe.db.commit()
    return out
