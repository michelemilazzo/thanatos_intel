# Thanatos Email + Drive + ERP + HelpDesk Integration

## Overview

Catena automatizzata: **Email arriva → riconosciuto cliente → linkato al caso → Drive folder pronto → quotation ERP generato → review report obbligatoria → invio**.

```
INBOUND EMAIL (cases@thanatos.agency)
    │ Frappe Email Account (IMAP fetch 5min)
    ↓
Communication doc inserted
    │ doc_event after_insert → intel_inbox.on_communication_insert
    ↓
PARSE sender email
    │ lookup Investigation Client by email
    ├── FOUND → cerca caso aperto
    │     │
    │     ├── caso esistente → link Communication.reference_doctype/name
    │     │   └── ensure_case_folder() crea/verifica /Cases/CASE-XXX/{Evidence,Reports,Email,Documents}
    │     └── nessun caso → link a Client (timeline cliente)
    │
    └── NOT FOUND → crea Lead (CRM) → fallback HelpDesk Ticket

OUTBOUND emails (responses)
    │ Frappe nativo: Communication thread Message-ID
    ↓
Auto-linked al doc origine via reply tracking nativo

CASE → ERPNEXT LOCALE (thanatos.onekeyco.com)
    │ internal_invoicing.py NUOVO
    ↓
Quotation/Sales Order/Sales Invoice creati sul DB locale (zero rete)
Customer = mapping da Investigation Client (idempotente)
Item = mapping da Service Catalog code (idempotente)
Pay-per-use → Sales Invoice diretto + Payment Entry (Stripe ref)

REPORT REVIEW
    │ workflow "Investigation Report Review" applicato
    ├── Draft → Pending Review (Investigator)
    ├── Pending Review → Approved/Rejected (Investigation Manager)
    ├── Approved → Sent (Manager)
    └── Sent → Archived
    │
    HOOK before_save/on_update blocca sendmail se review_status != Approved
```

## Componenti

### Frappe nativo già usato
- **Email Account** (IMAP+SMTP) — fetch automatic
- **Communication** — email-to-doc linking (reference_doctype/name) + threading Message-ID
- **CRM Lead** — fallback per email da sconosciuti
- **Drive File** (frappe/drive) — folder structure per caso
- **Workflow** — review states con role transitions
- **HelpDesk** (frappe/helpdesk) — ticket per non-clienti

### Custom Thanatos
- `integrations/intel_inbox.py` — auto-link Communication → Case + folder structure
- `billing/internal_invoicing.py` — **fatturazione clienti Thanatos via ERPNext locale (stesso DB)**
- `billing/erp_sync.py` — **separato**: tracking consumo infrastruttura + revenue fee dovuti a OneKeyCo, sync via REST verso `erp.onekeyco.com` (book-keeping esterno OneKeyCo, NON i clienti Thanatos)
- `fixtures/workflow.json` — workflow Investigation Report Review

### ⚠️ Due flussi di fatturazione separati
| Modulo | DB target | Cosa fattura | A chi |
|---|---|---|---|
| `internal_invoicing.py` | `thanatos.onekeyco.com` (locale, stesso bench) | Servizi investigativi, pay-per-use, abbonamenti | Clienti Thanatos (Avvocati, Aziende, Privati) |
| `erp_sync.py` | `erp.onekeyco.com` (remoto via REST) | Costi infrastruttura + revenue fee da Thanatos | OneKeyCo (società che eroga la piattaforma) |

## Email Account setup (operatore admin)

In Frappe Desk:
1. **Settings → Email Account → New**
2. Email: `cases@thanatos.agency`
3. IMAP host: stalwart MX
4. Enable incoming: ✓
5. Default Incoming: `Investigation Case`
6. Append To: Investigation Case
7. Auto Reply: ✗ (handled in custom flow)
8. Save

## Permission inheritance

| User Role | Cosa vede |
|---|---|
| **System Manager / Administrator** | Tutto |
| **Investigation Manager** | Tutti i casi della propria agenzia/team |
| **Investigator** | Solo casi assegnati (User Permission su `assigned_to`) |
| **Lawyer / Accountant** (external) | Solo casi del cliente loro affidato (User Permission su `client`) |
| **Investigation Client** (web user) | Solo i propri casi via portale `/portal/case/{name}` |
| **Compliance Officer** | Tutti, read-only su Evidence + Communication |
| **Customer** (basic) | Nessun caso, solo /pay-per-use checkout |

Implementato via `permissions.py` (già esistente) + `has_permission` hook in `hooks.py`.

## Report review obbligatoria

Hook `before_save`/`on_update` su Investigation Report:
- Default: review_status = "Draft" 
- Investigator submit → "Pending Review"  
- Investigation Manager approve → "Approved" + auto-stamp approved_by + approved_at
- Manager send → "Sent" (block if was not Approved)
- `frappe.throw("Un report può essere inviato solo dopo l'approvazione del responsabile.")`

## Automated reporting (futuro)

Report con `auto_generated=1` e `report_template in [...whitelisted simple...]` possono saltare review. Esempio:
- OSINT one-shot lookup (HIBP, RDAP, AbuseIPDB)
- Wallet crypto check rapido (€40-80 servizi `SVC-VR-010`)

Tutto il resto richiede review umana.

## HelpDesk attivazione

App `frappe/helpdesk` già installata. Da configurare:
1. Settings → HelpDesk Settings
2. Brand: Thanatos + colors (#0A0E1A / #C8A96E)
3. SLA policy: rispetta delivery_hours dal Service Catalog
4. Email integration: ticket@thanatos.agency
5. Customer portal: `/helpdesk` (esistente o custom redirect)

## TODO follow-up

- [ ] Configurare Email Account `cases@thanatos.agency` su stalwart mailmx
- [ ] Branding HelpDesk (colors + logo + workspace)
- [ ] Crea User Permission template per "Lawyer external"
- [ ] Connettere Investigation Case → Quotation (button "Generate Proforma")
- [ ] Drive folder structure con ownership inheritance
- [ ] Email template auto-reply per ack ricezione email
- [ ] Webhook quando Workflow transition Approved → notify client
- [ ] Test end-to-end: send email → vedere case timeline + folder + quotation
