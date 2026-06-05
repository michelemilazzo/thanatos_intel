# Email — Saltrade SDN BHD / Adwin J.K. James
**Da:** admin@thanatos.agency
**A:** adwinjkj@saltrade.co
**CC:** —
**Oggetto:** EN590-WLS-2026-001 — Signed mandate & pro forma — Operational expenses payment overdue
**Allegati richiesti:**
- THANATOS-EN590-WLS-2026-001-v5.pdf (signed mandate)
- THANATOS-ProForma-EN590-2026-001-EN.pdf (signed pro forma)

---

## Body (HTML/plain)

Dear Mr. Adwin Jeya Kumar James,

We hereby confirm that the signed documents related to the mandate have been duly executed and are attached to this email for your records:

- Signed mandate agreement (Ref. **EN590-WLS-2026-001**)
- Signed pro forma invoice (Ref. **PRF-EN590-2026-001**)

As clearly outlined in the documentation, the payment of the operational expenses (**EUR 5,000**) is a mandatory condition to activate the recovery procedure and initiate the immediate actions already defined.

To date, **we have not received the payment, nor any formal explanation for this delay.**

We must emphasize that:

- The beneficiary account remains active and currently not frozen
- The recovery window is extremely limited (10–15 days)
- Each day of delay significantly reduces the probability of recovery
- Failure to act promptly may result in irreversible loss of funds

Under these circumstances, your inaction is directly compromising the outcome of the case.

Therefore, we formally request:

1. **Immediate confirmation of payment execution**
2. **Transmission of payment proof (SWIFT / receipt)**
3. **Clarification regarding the reason for the delay**

**Deadline: within 24 hours from receipt of this email.**

Failing to receive confirmation within the above timeframe, we will consider:

- The mandate as not activated
- THANATOS released from any operational responsibility
- Any deterioration of recovery conditions as solely attributable to your delay

No protective or escalation actions can be initiated without the required funding.

This is a time-critical matter. **Immediate action is required.**

We expect your urgent response.

Kind regards,
**THANATOS INVESTIGAZIONI S.R.L.**
Constanta, Romania · CUI RO 46901022
admin@thanatos.agency · www.thanatos.agency
*Case Ref: EN590-WLS-2026-001*

---

## Per inviarla via Frappe

L'invio email da parte mia richiede tua autorizzazione esplicita per messaggio.
Quando confermi e mi indichi dove sono i 2 PDF allegati, eseguo:

```bash
ssh -i /root/.ssh/press_internal_id_ed25519 root@89.167.24.194 \
  "docker exec -i bench-0008-000007-aimc bash -lc 'cd /home/frappe/frappe-bench && bench --site thanatos.onekeyco.com console'"
```

```python
import frappe
frappe.connect()
frappe.sendmail(
    recipients=["adwinjkj@saltrade.co"],
    sender="admin@thanatos.agency",
    subject="EN590-WLS-2026-001 — Signed mandate & pro forma — Operational expenses payment overdue",
    message=open("/path/to/body.html").read(),
    attachments=[
        {"fname": "THANATOS-EN590-WLS-2026-001-v5.pdf",
         "fcontent": open("/path/to/mandate.pdf","rb").read()},
        {"fname": "THANATOS-ProForma-EN590-2026-001-EN.pdf",
         "fcontent": open("/path/to/proforma.pdf","rb").read()},
    ],
    now=True,
)
```
