"""Controller Facebook Post.

Ciclo di vita: Bozza -> Programmato -> Pubblicato (oppure Fallito / Annullato).
La pubblicazione effettiva passa dal client `integrations.facebook_graph`.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from thanatos_intel.integrations import facebook_graph as fb


class FacebookPost(Document):
    def validate(self):
        if self.post_type == "Link" and not (self.link or "").strip():
            frappe.throw("Per un post di tipo 'Link' devi indicare il campo Link.")
        if self.post_type == "Foto" and not (self.image or "").strip():
            frappe.throw("Per un post di tipo 'Foto' devi allegare un'immagine.")
        if self.post_type != "Foto":
            # Testo/Link devono avere del testo o un link.
            if not (self.message or "").strip() and not (self.link or "").strip():
                frappe.throw("Inserisci un testo o un link da pubblicare.")

    # -- azioni -------------------------------------------------------------

    @frappe.whitelist()
    def publish_now(self):
        """Pubblica subito il post sulla Pagina (ignora la programmazione)."""
        self._do_publish(scheduled_time=None)
        return self.status

    @frappe.whitelist()
    def schedule(self):
        """Segna il post come Programmato. Richiede scheduled_time futuro.

        Lo scheduler (`publish_due_posts`) lo pubblicherà alla data prevista.
        """
        if not self.scheduled_time:
            frappe.throw("Imposta prima 'Programmato per'.")
        if fb.get_datetime(self.scheduled_time) <= now_datetime():
            frappe.throw("La data di programmazione deve essere nel futuro.")
        self.db_set("status", "Programmato")
        self.db_set("error_log", "")
        return self.status

    @frappe.whitelist()
    def cancel_schedule(self):
        """Annulla un post programmato (non ancora pubblicato)."""
        if self.status == "Pubblicato":
            frappe.throw("Il post è già stato pubblicato: non può essere annullato qui.")
        self.db_set("status", "Annullato")
        return self.status

    @frappe.whitelist()
    def refresh_insights(self):
        """Aggiorna like/commenti/impression dal post pubblicato."""
        if not self.fb_post_id:
            frappe.throw("Nessun post pubblicato da aggiornare.")
        metrics = fb.fetch_post_metrics(self.fb_post_id)
        self._apply_metrics(metrics)
        return metrics

    # -- interno ------------------------------------------------------------

    def _do_publish(self, scheduled_time):
        if self.status == "Pubblicato":
            frappe.throw("Questo post è già stato pubblicato.")
        if not fb.is_enabled():
            frappe.throw(
                "Integrazione Facebook non attiva o non configurata "
                "(vedi Facebook Settings)."
            )
        message = self.message or ""
        link = self.link or None
        if not link and self.post_type != "Foto":
            default_link = _default_link()
            if default_link:
                link = default_link

        try:
            if self.post_type == "Foto":
                image_url = _absolute_file_url(self.image)
                res = fb.publish_photo(
                    image_url=image_url, caption=message,
                    scheduled_time=scheduled_time,
                )
            else:
                res = fb.publish_text(
                    message=message, link=link, scheduled_time=scheduled_time,
                )
        except Exception as e:
            self.db_set("status", "Fallito")
            self.db_set("error_log", str(e)[:1000])
            frappe.log_error(frappe.get_traceback(), "FacebookPost publish")
            raise

        post_id = res.get("id") or res.get("post_id") or ""
        self.db_set("fb_post_id", post_id)
        self.db_set("error_log", "")
        # Se abbiamo programmato nativamente su FB (>10 min), resta 'Programmato'.
        if scheduled_time and not res.get("id"):
            self.db_set("status", "Programmato")
        else:
            self.db_set("status", "Pubblicato")
            self.db_set("published_time", now_datetime())

    def _apply_metrics(self, metrics: dict):
        for key in ("impressions", "reach", "clicks", "likes", "comments", "shares"):
            if key in metrics:
                self.db_set(key, metrics[key])
        if metrics.get("permalink") and not self.permalink:
            self.db_set("permalink", metrics["permalink"])
        self.db_set("last_insights_sync", now_datetime())


def _default_link() -> str:
    try:
        s = fb.get_settings()
        # default_link vive solo sul DocType Facebook Settings.
        if frappe.db.exists("DocType", "Facebook Settings"):
            return frappe.db.get_single_value("Facebook Settings", "default_link") or ""
    except Exception:
        pass
    return ""


def _absolute_file_url(file_url: str) -> str:
    """Trasforma un /files/... privato o pubblico in URL assoluto per Graph API."""
    if not file_url:
        return ""
    if file_url.startswith("http://") or file_url.startswith("https://"):
        return file_url
    base = frappe.utils.get_url()
    return f"{base}{file_url}"


# ---------------------------------------------------------------------------
# Scheduler jobs (registrati in hooks.scheduler_events)
# ---------------------------------------------------------------------------

def publish_due_posts():
    """Pubblica i Facebook Post 'Programmato' la cui data è scaduta.

    Chiamato dallo scheduler ogni pochi minuti. No-op se l'integrazione è
    disattiva o se l'auto-publish è spento in Facebook Settings.
    """
    if not fb.is_enabled():
        return
    if frappe.db.exists("DocType", "Facebook Settings"):
        if not frappe.db.get_single_value("Facebook Settings", "auto_publish_scheduler"):
            return

    due = frappe.get_all(
        "Facebook Post",
        filters={"status": "Programmato", "scheduled_time": ["<=", now_datetime()]},
        pluck="name",
    )
    for name in due:
        try:
            doc = frappe.get_doc("Facebook Post", name)
            doc._do_publish(scheduled_time=None)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), f"publish_due_posts {name}")


def refresh_published_insights(days: int = 30):
    """Aggiorna gli insights dei post pubblicati di recente."""
    if not fb.is_enabled():
        return
    from frappe.utils import add_days

    names = frappe.get_all(
        "Facebook Post",
        filters={
            "status": "Pubblicato",
            "fb_post_id": ["!=", ""],
            "published_time": [">=", add_days(now_datetime(), -abs(days))],
        },
        pluck="name",
    )
    for name in names:
        try:
            doc = frappe.get_doc("Facebook Post", name)
            metrics = fb.fetch_post_metrics(doc.fb_post_id)
            doc._apply_metrics(metrics)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), f"refresh_insights {name}")
