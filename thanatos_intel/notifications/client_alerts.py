"""
Notifiche periodiche ai clienti Thanatos: scadenze vault, verifica dati, coerenza KYC.
Tutte le email sono bilingue: italiano (lingua preferita cliente) + inglese sempre.
"""
import frappe
from frappe.utils import today, add_days

_EXPIRY_THRESHOLDS = [60, 30, 15, 7, 1]

_VAULT_EXPIRY_IT = """
<p>Gentile {client_name},</p>
<p>Il documento <b>{doc_kind}</b> nel tuo archivio personale <b>scade il {valid_until}</b> ({days_left} giorni).</p>
<p>Ti chiediamo di rinnovarlo e caricare una copia aggiornata nel portale per mantenere la validità del tuo profilo.</p>
<p><a href="{vault_url}" style="background:#1a1a2e;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;display:inline-block;">Vai all'archivio documenti</a></p>
"""

_VAULT_EXPIRY_EN = """
<p>Dear {client_name},</p>
<p>The document <b>{doc_kind}</b> in your personal archive <b>expires on {valid_until}</b> ({days_left} days remaining).</p>
<p>Please upload an updated copy to maintain your profile validity.</p>
<p><a href="{vault_url}" style="background:#1a1a2e;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;display:inline-block;">Go to document archive</a></p>
"""

_DATA_VERIFY_IT = """
<p>Gentile {client_name},</p>
<p>Sono trascorsi più di 6 mesi dall'ultima verifica dei tuoi dati. Per garantire la correttezza delle informazioni nel nostro sistema, ti chiediamo di confermare o aggiornare il tuo profilo.</p>
<p>Se le tue informazioni sono cambiate (contatti, indirizzo, azienda, ecc.), accedi al portale e aggiornale.</p>
<p><a href="{profile_url}" style="background:#1a1a2e;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;display:inline-block;">Verifica i tuoi dati</a></p>
<p style="color:#888;font-size:13px;">Se i tuoi dati sono corretti, puoi ignorare questa email.</p>
"""

_DATA_VERIFY_EN = """
<p>Dear {client_name},</p>
<p>More than 6 months have passed since we last verified your information. To ensure the accuracy of our records, please confirm or update your profile.</p>
<p>If your details have changed (contact info, address, company, etc.), log in to the portal and update them.</p>
<p><a href="{profile_url}" style="background:#1a1a2e;color:#fff;padding:10px 20px;border-radius:4px;text-decoration:none;display:inline-block;">Review your details</a></p>
<p style="color:#888;font-size:13px;">If your details are correct, you may ignore this email.</p>
"""


def _base_url():
    return frappe.utils.get_url()


def _preferred_lang(client_name):
    lang = frappe.db.get_value("Investigation Client", client_name, "preferred_language")
    return lang or "Italian"


def _send_bilingual(to_email, subject_it, subject_en, body_it, body_en):
    combined = (
        "<div style='max-width:600px;margin:0 auto;font-family:sans-serif;'>"
        f"{body_it}"
        "<hr style='margin:28px 0;border:none;border-top:1px solid #e0e0e0;'>"
        "<p style='color:#aaa;font-size:11px;font-style:italic;'>English / Anglais:</p>"
        f"{body_en}"
        "</div>"
    )
    frappe.sendmail(
        recipients=[to_email],
        subject=f"{subject_it} / {subject_en}",
        message=combined,
        with_container=True,
        header=["Thanatos Intel", "blue"],
        reply_to="cases@thanatos.agency",
    )


def daily_vault_expiry_check():
    """Notifica scadenze vault imminenti: 60/30/15/7/1 giorni prima."""
    td = today()
    for days in _EXPIRY_THRESHOLDS:
        target = add_days(td, days)
        items = frappe.db.sql("""
            SELECT cvi.name, cvi.client, cvi.doc_kind, cvi.valid_until,
                   ic.email, ic.client_name
            FROM `tabClient Vault Item` cvi
            JOIN `tabInvestigation Client` ic ON ic.name = cvi.client
            WHERE DATE(cvi.valid_until) = %s
              AND cvi.status = 'Valido'
              AND ic.email IS NOT NULL AND ic.email != ''
        """, (target,), as_dict=True)

        vault_url = f"{_base_url()}/portal/vault"
        for item in items:
            ctx = {
                "client_name": item.client_name,
                "doc_kind": item.doc_kind,
                "valid_until": str(item.valid_until),
                "days_left": days,
                "vault_url": vault_url,
            }
            try:
                _send_bilingual(
                    to_email=item.email,
                    subject_it=f"Documento in scadenza: {item.doc_kind} ({days}gg)",
                    subject_en=f"Document expiring: {item.doc_kind} ({days} days)",
                    body_it=_VAULT_EXPIRY_IT.format(**ctx),
                    body_en=_VAULT_EXPIRY_EN.format(**ctx),
                )
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"vault_expiry_notify {item.name}")


def monthly_data_verification_request():
    """Invia richiesta verifica dati ai clienti non aggiornati da più di 180 giorni."""
    cutoff = add_days(today(), -180)
    clients = frappe.db.sql("""
        SELECT name, email, client_name, modified
        FROM `tabInvestigation Client`
        WHERE email IS NOT NULL AND email != ''
          AND onboarding_status IN ('Active', 'Under Review', 'Completed', 'Active - No Card')
          AND DATE(modified) < %s
    """, (cutoff,), as_dict=True)

    profile_url = f"{_base_url()}/portal/profile"
    for cl in clients:
        ctx = {"client_name": cl.client_name, "profile_url": profile_url}
        try:
            _send_bilingual(
                to_email=cl.email,
                subject_it="Conferma i tuoi dati — Thanatos Intel",
                subject_en="Please verify your details — Thanatos Intel",
                body_it=_DATA_VERIFY_IT.format(**ctx),
                body_en=_DATA_VERIFY_EN.format(**ctx),
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"data_verify_notify {cl.name}")


def daily_pending_payment_reminder():
    """Ricorda ai clienti i Usage Events Pending da più di 7 giorni."""
    cutoff_7 = add_days(today(), -7)
    cutoff_30 = add_days(today(), -30)

    # Clienti con almeno un evento pending vecchio ≥7 giorni e < 30 (già avvisati a 7)
    rows = frappe.db.sql("""
        SELECT ue.client, ic.email, ic.client_name,
               COUNT(ue.name) AS n_pending,
               SUM(ue.total) AS total_due,
               MAX(ue.currency) AS currency
        FROM `tabUsage Event` ue
        JOIN `tabInvestigation Client` ic ON ic.name = ue.client
        WHERE ue.status = 'Pending'
          AND DATE(ue.creation) <= %s
          AND DATE(ue.creation) > %s
          AND ic.email IS NOT NULL AND ic.email != ''
        GROUP BY ue.client, ic.email, ic.client_name
    """, (cutoff_7, cutoff_30), as_dict=True)

    billing_url = f"{_base_url()}/portal/invoices"
    for r in rows:
        try:
            total_str = f"{float(r.total_due or 0):.2f} {r.currency or 'EUR'}"
            body_it = (
                f"<p>Gentile {r.client_name},</p>"
                f"<p>Hai <strong>{r.n_pending} servizi</strong> in attesa di pagamento "
                f"per un totale di <strong>{total_str}</strong>.</p>"
                f"<p><a href='{billing_url}' style='background:#C8A96E;color:#0A0E1A;"
                f"padding:10px 20px;border-radius:4px;text-decoration:none;"
                f"display:inline-block;font-weight:bold'>Vai alle fatture →</a></p>"
            )
            body_en = (
                f"<p>Dear {r.client_name},</p>"
                f"<p>You have <strong>{r.n_pending} service(s)</strong> awaiting payment "
                f"totalling <strong>{total_str}</strong>.</p>"
                f"<p><a href='{billing_url}' style='background:#C8A96E;color:#0A0E1A;"
                f"padding:10px 20px;border-radius:4px;text-decoration:none;"
                f"display:inline-block;font-weight:bold'>View invoices →</a></p>"
            )
            _send_bilingual(
                to_email=r.email,
                subject_it=f"Pagamenti in sospeso ({total_str}) — Thanatos Intel",
                subject_en=f"Pending payment ({total_str}) — Thanatos Intel",
                body_it=body_it, body_en=body_en,
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             f"pending_payment_reminder {r.client}")


def daily_operator_digest():
    """Digest giornaliero per operatori: casi aperti con step in attesa di azione."""
    open_cases = frappe.db.sql("""
        SELECT ic.name, ic.case_number, ic.case_title, ic.status,
               ic.assigned_to, ic.priority,
               COUNT(cs.name) AS pending_steps
        FROM `tabInvestigation Case` ic
        LEFT JOIN `tabCase Step` cs ON cs.parent = ic.name
            AND cs.status IN ('In Progress', 'Awaiting Client', 'current')
        WHERE ic.status NOT IN ('Closed', 'Cancelled', 'Completed', 'Archived')
        GROUP BY ic.name, ic.case_number, ic.case_title, ic.status,
                 ic.assigned_to, ic.priority
        ORDER BY ic.priority DESC, ic.creation ASC
        LIMIT 50
    """, as_dict=True)

    if not open_cases:
        return

    # Raggruppa per operatore assegnato
    by_op = {}
    unassigned = []
    for c in open_cases:
        op = c.assigned_to
        if op:
            by_op.setdefault(op, []).append(c)
        else:
            unassigned.append(c)

    def _case_rows(cases):
        rows = ""
        for c in cases:
            rows += (
                f"<tr>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>"
                f"<a href='{frappe.utils.get_url()}/app/investigation-case/{c.name}'>"
                f"{c.case_number or c.name}</a></td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>"
                f"{c.case_title or '—'}</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>"
                f"{c.status}</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #eee;text-align:center'>"
                f"{c.pending_steps or 0}</td>"
                f"</tr>"
            )
        return rows

    def _table(cases):
        return (
            "<table style='width:100%;border-collapse:collapse;font-size:13px'>"
            "<thead><tr style='background:#f0f0f0'>"
            "<th style='padding:6px 10px;text-align:left'>Caso</th>"
            "<th style='padding:6px 10px;text-align:left'>Titolo</th>"
            "<th style='padding:6px 10px;text-align:left'>Stato</th>"
            "<th style='padding:6px 10px;text-align:center'>Step pendenti</th>"
            f"</tr></thead><tbody>{_case_rows(cases)}</tbody></table>"
        )

    # Invia digest personale a ogni operatore
    for op_email, cases in by_op.items():
        try:
            name = frappe.db.get_value("User", op_email, "full_name") or op_email
            frappe.sendmail(
                recipients=[op_email],
                subject=f"[Thanatos] Digest giornaliero — {len(cases)} casi assegnati",
                message=(
                    f"<div style='font-family:sans-serif;max-width:700px'>"
                    f"<p>Ciao {name}, ecco i tuoi casi aperti:</p>"
                    f"{_table(cases)}"
                    f"<p style='color:#888;font-size:12px;margin-top:20px'>"
                    f"<a href='{frappe.utils.get_url()}/portal/ops'>Centro Operativo →</a></p>"
                    f"</div>"
                ),
                delayed=True,
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"operator_digest {op_email}")

    # Digest admin per casi non assegnati
    if unassigned:
        try:
            frappe.sendmail(
                recipients=["admin@thanatos.agency"],
                subject=f"[Thanatos] {len(unassigned)} casi senza assegnatario",
                message=(
                    f"<div style='font-family:sans-serif;max-width:700px'>"
                    f"<p>I seguenti casi sono aperti ma senza investigatore assegnato:</p>"
                    f"{_table(unassigned)}</div>"
                ),
                delayed=True,
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "operator_digest_unassigned")


def check_kyc_onboarding_consistency():
    """Notifica interna per clienti con KYC=Passed ma onboarding non completato."""
    COMPLETED = ("Active", "Completed", "Active - No Card")
    placeholders = ",".join(["%s"] * len(COMPLETED))
    mismatches = frappe.db.sql(f"""
        SELECT name, client_name, kyc_status, onboarding_status
        FROM `tabInvestigation Client`
        WHERE kyc_status = 'Passed'
          AND onboarding_status NOT IN ({placeholders})
    """, COMPLETED, as_dict=True)

    if not mismatches:
        return

    rows = "".join(
        f"<tr><td style='padding:4px 8px;border:1px solid #ddd'>{m.name}</td>"
        f"<td style='padding:4px 8px;border:1px solid #ddd'>{m.client_name}</td>"
        f"<td style='padding:4px 8px;border:1px solid #ddd'>{m.kyc_status}</td>"
        f"<td style='padding:4px 8px;border:1px solid #ddd'>{m.onboarding_status}</td></tr>"
        for m in mismatches
    )
    table = (
        "<table style='border-collapse:collapse;width:100%'>"
        "<thead><tr style='background:#f5f5f5'>"
        "<th style='padding:4px 8px;border:1px solid #ddd'>ID</th>"
        "<th style='padding:4px 8px;border:1px solid #ddd'>Nome</th>"
        "<th style='padding:4px 8px;border:1px solid #ddd'>KYC</th>"
        "<th style='padding:4px 8px;border:1px solid #ddd'>Onboarding</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
    body = (
        f"<p>I seguenti {len(mismatches)} clienti hanno KYC approvato ma onboarding incompleto. "
        f"Verificare manualmente.</p>{table}"
        "<hr>"
        f"<p>The following {len(mismatches)} clients have passed KYC but incomplete onboarding. "
        f"Please review manually.</p>{table}"
    )
    try:
        frappe.sendmail(
            recipients=["cases@thanatos.agency"],
            subject=f"[Thanatos] KYC/Onboarding mismatch: {len(mismatches)} clienti",
            message=f"<div style='font-family:sans-serif;max-width:700px'>{body}</div>",
            with_container=True,
            header=["Thanatos Intel Admin", "red"],
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "kyc_onboarding_consistency_notify")
