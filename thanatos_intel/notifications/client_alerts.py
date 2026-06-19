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
