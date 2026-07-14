# Automazione Facebook (Thanatos ➜ Pagina)

Modulo **Thanatos Social**: gestione e pubblicazione dei contenuti della
Pagina Facebook Thanatos direttamente dal bench, con programmazione e lettura
degli Insights.

## Componenti

| Componente | Percorso | Ruolo |
|---|---|---|
| Client Graph API | `thanatos_intel/integrations/facebook_graph.py` | Pubblica testo/link/foto, legge insights |
| `Facebook Settings` (Single) | `thanatos_social/doctype/facebook_settings` | Credenziali Pagina + toggle auto-publish |
| `Facebook Post` | `thanatos_social/doctype/facebook_post` | Contenuto: Bozza ➜ Programmato ➜ Pubblicato |
| API | `thanatos_social/api.py` | `quick_post`, `page_insights` |
| Scheduler | hooks `scheduler_events` | pubblica i post programmati, aggiorna insights |

## Configurazione

1. Crea un'app su [developers.facebook.com](https://developers.facebook.com)
   con prodotto **Facebook Login**.
2. Assegna i permessi: `pages_manage_posts`, `pages_read_engagement`,
   `pages_read_user_content`, `read_insights`, `business_management`.
3. Ottieni un **Page Access Token** long-lived della Pagina Thanatos
   (User Token ➜ scambio long-lived ➜ `/me/accounts`).
4. Inseriscilo in **Facebook Settings** (`/app/facebook-settings`) e spunta
   *Integrazione attiva*, oppure in `site_config.json`:

   ```json
   {
     "facebook_enabled": 1,
     "facebook_page_id": "1234567890",
     "facebook_page_token": "EAAB...",
     "facebook_api_version": "v19.0"
   }
   ```

5. Usa **Verifica connessione** per controllare token e nome Pagina.

## Uso

- **Manuale**: crea un `Facebook Post`, scegli il tipo (Testo / Link / Foto),
  poi *Pubblica ora* oppure imposta *Programmato per* e *Programma*.
- **Programmato**: lo scheduler (`publish_due_posts`, ogni 5 min) pubblica i
  post arrivati a scadenza. I post con scadenza > 10 minuti usano la
  programmazione nativa di Facebook.
- **Programmatico**: da altri flussi Thanatos

  ```python
  frappe.call("thanatos_intel.thanatos_social.api.quick_post",
              message="Nuovo report disponibile", link="https://thanatos.agency")
  ```

- **Insights**: pulsante *Aggiorna Insights* sul post, oppure job orario
  `refresh_published_insights`. Insights di Pagina via
  `thanatos_intel.thanatos_social.api.page_insights`.

## Note

- Senza credenziali il modulo è un **no-op**: non rompe il resto dell'app
  (stesso pattern di `waba_notifications` / `telegram_channel`).
- Gli errori di pubblicazione finiscono in `error_log` sul post e nell'Error
  Log di Frappe (`facebook_graph error`).
