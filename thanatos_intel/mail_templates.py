"""
thanatos_intel/mail_templates.py

API per creare bozze email nel webmail da Agency Mandate / Diplomatic Eligibility Case.
Ogni funzione crea la bozza via mail.api.mail.create_mail(save_as_draft=True)
e restituisce {"draft_id": ..., "mail_url": "/mail"}.
"""

import frappe
from frappe import _
from frappe.utils.password import get_decrypted_password


def _get_from_email(user: str) -> str:
    us = frappe.db.get_value("User Settings", {"user": user}, "username")
    if not us:
        frappe.throw(_("Configura prima l'account email nel webmail (User Settings)."))
    return us


def _create_draft(from_email: str, to: list, subject: str, html_body: str, cc: list | None = None) -> dict:
    from mail.api.mail import create_mail
    # Risolvi "account" (Mail upstream >=0.2: arg obbligatorio)
    import frappe as _f
    # account in formato 'user:account_id' (Mail upstream >=0.2)
    # 1) Helper mail nativo (se disponibile)
    account = None
    try:
        from mail.utils.user import get_user_personal_account
        account = get_user_personal_account(_f.session.user)
    except Exception:
        pass
    # 2) Fallback: cerca User Account → first matching by email
    if not account:
        try:
            ua = _f.db.get_value("User Account", {"email": from_email}, "name")
            if ua: account = ua
        except Exception:
            pass
    # 3) Fallback finale: <user>:<from_email>
    if not account:
        account = f"{_f.session.user}:{from_email}"
    # Normalizza destinatari: create_mail si aspetta list[dict] con chiave 'email'
    def _norm(addrs):
        out = []
        for a in (addrs or []):
            if isinstance(a, dict):
                out.append({"email": a.get("email") or a.get("address"), "display_name": a.get("display_name","")})
            else:
                out.append({"email": str(a), "display_name": ""})
        return out
    result = create_mail(
        account=account,
        from_email=from_email,
        to=_norm(to),
        cc=_norm(cc),
        bcc=[],
        subject=subject,
        html_body=html_body,
        attachments=[],
        save_as_draft=True,
    )
    return {"draft_id": result.get("id"), "mail_url": "/mail", "account": account}


def _client_email(applicant_id: str) -> str | None:
    if not applicant_id:
        return None
    return frappe.db.get_value("Investigation Client", applicant_id, "email")


def _client_name(applicant_id: str) -> str:
    if not applicant_id:
        return ""
    return frappe.db.get_value("Investigation Client", applicant_id, "client_name") or ""


# ─── TEMPLATE 1: Proposta DDD / Offerta commerciale ────────────────────────────

@frappe.whitelist()
def draft_ddd_offer(mandate_name: str) -> dict:
    """Crea bozza email proposta DDD da Agency Mandate."""
    user = frappe.session.user
    from_email = _get_from_email(user)

    m = frappe.get_doc("Agency Mandate", mandate_name)
    client_email = _client_email(m.applicant)
    client_name = _client_name(m.applicant)

    # Carica DDD Case se collegato
    country = ""
    risk_band = ""
    workflow_state = ""
    if m.ddd_case:
        c = frappe.get_doc("Diplomatic Eligibility Case", m.ddd_case)
        country = c.country or ""
        risk_band = c.risk_band or ""
        workflow_state = c.workflow_state or ""

    subject = f"Proposta Due Diligence Diplomatica {country} — {client_name or mandate_name}"
    case_url = f"https://thanatos.agency/app/diplomatic-eligibility-case/{m.ddd_case}" if m.ddd_case else ""
    mandate_url = f"https://thanatos.agency/app/agency-mandate/{mandate_name}"

    html = f"""
<p>Gentile {client_name or 'Cliente'},</p>
<p>Con la presente Le trasmettiamo la nostra offerta commerciale per il servizio di 
<strong>Due Diligence Diplomatica</strong> relativo al Paese di destinazione: <strong>{country}</strong>.</p>

<h3>Dettagli Pratica</h3>
<table style="border-collapse:collapse;width:100%">
  <tr><td style="padding:4px 8px;font-weight:bold">Rif. Mandato</td><td style="padding:4px 8px">{mandate_name}</td></tr>
  <tr><td style="padding:4px 8px;font-weight:bold">Pratica DDD</td><td style="padding:4px 8px">{m.ddd_case or '—'}</td></tr>
  <tr><td style="padding:4px 8px;font-weight:bold">Paese</td><td style="padding:4px 8px">{country}</td></tr>
  <tr><td style="padding:4px 8px;font-weight:bold">Importo preventivato</td><td style="padding:4px 8px">EUR {m.fee_total:,.2f}</td></tr>
  <tr><td style="padding:4px 8px;font-weight:bold">Stato pratica</td><td style="padding:4px 8px">{workflow_state}</td></tr>
</table>

<p>{"<strong>Risk Band preliminare:</strong> " + risk_band + "<br>" if risk_band else ""}
{"<a href='" + case_url + "'>Visualizza pratica DDD</a> | " if case_url else ""}
<a href='{mandate_url}'>Visualizza Mandato</a></p>

<p>Rimaniamo a disposizione per qualsiasi chiarimento.</p>

<p>Cordiali saluti,<br>
<strong>ARES INVESTIGAZIONI SRL</strong><br>
Agenzia Investigativa — art. 134 TULPS<br>
<em>thanatos.agency</em></p>
"""
    return _create_draft(from_email, [client_email] if client_email else [], subject, html)


# ─── TEMPLATE 2: Richiesta KYC/KYB ────────────────────────────────────────────

@frappe.whitelist()
def draft_kyc_request(case_name: str) -> dict:
    """Crea bozza richiesta KYC/KYB da Diplomatic Eligibility Case."""
    user = frappe.session.user
    from_email = _get_from_email(user)

    c = frappe.get_doc("Diplomatic Eligibility Case", case_name)
    client_email = _client_email(c.applicant)
    client_name = _client_name(c.applicant)
    country = c.country or ""
    case_url = f"https://thanatos.agency/app/diplomatic-eligibility-case/{case_name}"

    subject = f"Richiesta documentazione KYC/KYB — Pratica {case_name} — {country}"

    html = f"""
<p>Gentile {client_name or 'Cliente'},</p>
<p>In riferimento alla pratica <strong>{case_name}</strong> relativa al Paese di destinazione 
<strong>{country}</strong>, per procedere con la due diligence diplomatica siamo tenuti a 
raccogliere la seguente documentazione:</p>

<h3>Documenti KYC richiesti (Persona Fisica)</h3>
<ul>
  <li>Copia fronte/retro documento d'identità in corso di validità (passaporto o carta d'identità)</li>
  <li>Copia codice fiscale / documento equivalente</li>
  <li>Prova di residenza (bolletta o estratto conto bancario, non oltre 3 mesi)</li>
  <li>Dichiarazione di origine fondi (se richiesta)</li>
</ul>

<h3>Documenti KYB richiesti (Società / Studio Legale)</h3>
<ul>
  <li>Visura camerale aggiornata (non oltre 6 mesi)</li>
  <li>Atto costitutivo e statuto vigente</li>
  <li>Lista soci/titolari effettivi (UBO Declaration)</li>
  <li>Documento d'identità del rappresentante legale</li>
</ul>

<p><strong>Rif. Pratica:</strong> <a href='{case_url}'>{case_name}</a></p>
<p>Si prega di inviare la documentazione in formato PDF firmata digitalmente o scansionata in alta risoluzione.</p>

<p>Cordiali saluti,<br>
<strong>ARES INVESTIGAZIONI SRL</strong><br>
Agenzia Investigativa — art. 134 TULPS<br>
<em>thanatos.agency</em></p>
"""
    return _create_draft(from_email, [client_email] if client_email else [], subject, html)


# ─── TEMPLATE 3: Mandato pronto per firma ─────────────────────────────────────

@frappe.whitelist()
def draft_mandate_signing(mandate_name: str) -> dict:
    """Crea bozza email invio link firma mandato."""
    user = frappe.session.user
    from_email = _get_from_email(user)

    m = frappe.get_doc("Agency Mandate", mandate_name)
    client_email = _client_email(m.applicant)
    client_name = _client_name(m.applicant)
    signing_url = ""
    country = ""
    if m.ddd_case:
        country = frappe.db.get_value("Diplomatic Eligibility Case", m.ddd_case, "country") or ""

    subject = f"Mandato di incarico pronto per la firma — {country} — {mandate_name}"

    html = f"""
<p>Gentile {client_name or 'Cliente'},</p>
<p>Il mandato di incarico per la pratica di Due Diligence Diplomatica relativa a 
<strong>{country}</strong> è pronto per la firma digitale.</p>

<table style="border-collapse:collapse;width:100%">
  <tr><td style="padding:4px 8px;font-weight:bold">Rif. Mandato</td><td style="padding:4px 8px">{mandate_name}</td></tr>
  <tr><td style="padding:4px 8px;font-weight:bold">Importo</td><td style="padding:4px 8px">EUR {m.fee_total:,.2f}</td></tr>
  <tr><td style="padding:4px 8px;font-weight:bold">Entità emittente</td><td style="padding:4px 8px">{m.billing_entity or 'ARES INVESTIGAZIONI SRL'}</td></tr>
</table>

{"<p><a href='" + signing_url + "' style='background:#1a1a2e;color:#fff;padding:12px 24px;text-decoration:none;border-radius:4px;display:inline-block;margin-top:12px'>➤ Firma il Mandato</a></p>" if signing_url else "<p><em>(Link firma non ancora disponibile)</em></p>"}

<p>La firma è richiesta tramite la piattaforma sicura MMOS Sign. Il processo richiede meno di 2 minuti.</p>
<p>Una volta firmato il documento, riceverà automaticamente una copia via email.</p>

<p>Cordiali saluti,<br>
<strong>ARES INVESTIGAZIONI SRL</strong><br>
Agenzia Investigativa — art. 134 TULPS<br>
<em>thanatos.agency</em></p>
"""
    return _create_draft(from_email, [client_email] if client_email else [], subject, html)


# ─── TEMPLATE 4: Aggiornamento stato pratica ──────────────────────────────────

@frappe.whitelist()
def draft_status_update(case_name: str) -> dict:
    """Crea bozza aggiornamento stato da Diplomatic Eligibility Case."""
    user = frappe.session.user
    from_email = _get_from_email(user)

    c = frappe.get_doc("Diplomatic Eligibility Case", case_name)
    client_email = _client_email(c.applicant)
    client_name = _client_name(c.applicant)
    country = c.country or ""
    state = c.workflow_state or ""
    case_url = f"https://thanatos.agency/app/diplomatic-eligibility-case/{case_name}"

    subject = f"Aggiornamento pratica DDD {case_name} — {country} — {state}"

    state_messages = {
        "KYC Pending": "Siamo in attesa della documentazione KYC/KYB richiesta. Si prega di procedere all'invio al più presto.",
        "KYC Review": "La documentazione KYC/KYB ricevuta è in fase di verifica da parte del nostro team.",
        "Questionnaire Pending": "Il questionario di due diligence è disponibile per la compilazione.",
        "Analysis In Progress": "L'analisi di due diligence diplomatica è in corso. Le forniremo gli esiti entro i termini concordati.",
        "Report Ready": "Il report di due diligence è stato completato ed è disponibile nel portale.",
        "Closed": "La pratica è stata chiusa.",
    }
    state_msg = state_messages.get(state, f"Lo stato della pratica è aggiornato a: <strong>{state}</strong>.")

    html = f"""
<p>Gentile {client_name or 'Cliente'},</p>
<p>La informiamo che la pratica <strong>{case_name}</strong> — Due Diligence Diplomatica 
<strong>{country}</strong> — ha ricevuto il seguente aggiornamento:</p>

<div style="background:#f5f5f5;border-left:4px solid #1a1a2e;padding:12px 16px;margin:16px 0">
  <strong>Stato attuale:</strong> {state}<br>
  {state_msg}
</div>

{'<p><strong>Livello di rischio:</strong> ' + c.risk_band + '</p>' if c.risk_band else ''}
{'<p><strong>Decisione finale:</strong> ' + c.final_decision + '</p>' if c.final_decision else ''}

<p><a href='{case_url}'>Accedi al portale per i dettagli →</a></p>

<p>Per qualsiasi informazione siamo a sua disposizione.</p>

<p>Cordiali saluti,<br>
<strong>ARES INVESTIGAZIONI SRL</strong><br>
Agenzia Investigativa — art. 134 TULPS<br>
<em>thanatos.agency</em></p>
"""
    return _create_draft(from_email, [client_email] if client_email else [], subject, html)
