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


@frappe.whitelist()
def case_documents(case):
    """Elenco dei documenti (File) allegati al caso con la loro visibilita' cliente
    e se sono gia' pubblicati nel portale del cliente."""
    if not case or not frappe.db.exists("Investigation Case", case):
        return {"documents": [], "has_client": False}
    has_client = bool(frappe.db.get_value("Investigation Case", case, "client"))
    files = frappe.get_all("File",
        filters={"attached_to_doctype": "Investigation Case", "attached_to_name": case},
        fields=["name", "file_name", "file_url", "is_private",
                "visibilita_cliente", "vault_published"],
        order_by="creation desc")
    docs = []
    for f in files:
        docs.append({
            "name": f.name,
            "file_name": f.file_name or f.file_url,
            "file_url": f.file_url,
            "visibilita": f.visibilita_cliente or "Solo interno",
            "published": bool(f.vault_published),
        })
    return {"documents": docs, "has_client": has_client}


@frappe.whitelist()
def set_document_visibility(file, visibilita):
    """Imposta la visibilita' cliente di un singolo File (Solo interno / Condiviso col cliente)."""
    if visibilita not in ("Solo interno", "Condiviso col cliente"):
        frappe.throw("Visibilita' non valida")
    frappe.db.set_value("File", file, "visibilita_cliente", visibilita, update_modified=False)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
def publish_shared_documents(case, share_all=0):
    """Pubblica nel portale del cliente i documenti del caso marcati 'Condiviso col cliente'
    (o tutti, se share_all=1). I 'Solo interno' restano riservati allo staff."""
    share_all = int(share_all or 0)
    if not frappe.db.get_value("Investigation Case", case, "client"):
        return {"ok": False, "error": "Il caso non ha un cliente collegato: impossibile pubblicare."}
    files = frappe.get_all("File",
        filters={"attached_to_doctype": "Investigation Case", "attached_to_name": case},
        fields=["name", "file_name", "file_url", "visibilita_cliente", "vault_published"])
    published, skipped = 0, 0
    for f in files:
        share = share_all or (f.visibilita_cliente == "Condiviso col cliente")
        if not share:
            skipped += 1
            continue
        if share_all and f.visibilita_cliente != "Condiviso col cliente":
            frappe.db.set_value("File", f.name, "visibilita_cliente", "Condiviso col cliente", update_modified=False)
        if f.vault_published:
            continue
        try:
            deliver_case_file(case, f.file_url, file_name=f.file_name,
                              doc_kind="Altro", self_mode=1, notify_email=0)
            frappe.db.set_value("File", f.name, "vault_published", 1, update_modified=False)
            published += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "publish_shared_documents")
    frappe.db.commit()
    return {"ok": True, "published": published, "internal_kept": skipped}
