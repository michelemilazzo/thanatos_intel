import frappe
from frappe.model.document import Document


class ClientLegacyDelegate(Document):
    def before_insert(self):
        import secrets
        self.invite_token = secrets.token_urlsafe(32)

    def on_update(self):
        if self.status == "Granted" and not self.access_token:
            import secrets
            from frappe.utils import now_datetime, add_days
            self.access_token = secrets.token_urlsafe(32)
            self.granted_at = now_datetime()
            self.access_expires_at = add_days(now_datetime(), int(self.access_days or 30))
            self.db_update()
            self._notify_delegate_access_granted()

    def _notify_delegate_access_granted(self):
        try:
            client_name = frappe.db.get_value("Investigation Client", self.client, "client_name") or self.client
            url = f"https://thanatos.agency/portal/legacy/view?token={self.access_token}"
            frappe.sendmail(
                recipients=[self.delegate_email],
                subject=f"Accesso Legacy Digitale — {client_name} | Thanatos Intel",
                message=f"""
<p>Gentile {self.delegate_name},</p>
<p>La sua richiesta di accesso Legacy Digitale per il fascicolo di <strong>{client_name}</strong>
è stata approvata da Thanatos Intel.</p>
<p>Può accedere ai documenti e alle pratiche tramite il link seguente:</p>
<p><a href="{url}" style="background:#C8A96E;color:#0A0E1A;padding:12px 24px;text-decoration:none;display:inline-block"
>Accedi al fascicolo →</a></p>
<p>L'accesso scade il <strong>{frappe.utils.format_datetime(self.access_expires_at, "dd/MM/yyyy")}</strong>.</p>
<p style="color:#666;font-size:12px">Thanatos Intel · uso riservato · non condividere questo link</p>
""",
                now=True,
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Legacy delegate grant notification failed")
