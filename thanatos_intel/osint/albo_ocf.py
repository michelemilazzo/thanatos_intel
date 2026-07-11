"""Ricerca semi-automatica nell'Albo OCF (consulenti finanziari) via Playwright.

OCF (organismocf.it) rende i risultati via JavaScript (DataTables) e protegge la
ricerca con CAPTCHA -> impossibile scraping HTTP puro. Flusso semi-automatico:
il bot apre il browser headless, compila cognome/nome/sezione, manda l'immagine
del captcha all'operatore su WhatsApp, attende che l'operatore lo risolva, poi
completa la ricerca e restituisce i risultati parsati. Il captcha lo risolve un
UMANO (nessun aggiramento anti-bot).

Selettori (mappati 2026-07-11): cognome=#cognome, nome=#nome,
sezione=#sezione_albo (''=tutte/CFF/CFA/SCF), captcha img=#captchaImg,
captcha input=#captchaInput, submit=#submitRicercaConsulenteButton,
risultati=#tableContainerBody tr.
"""
import time
import frappe
from frappe.utils import now_datetime

OCF_URL = "https://www.organismocf.it/portal/web/portale-ocf/ricerca-nelle-sezioni-dell-albo"
_SEZIONI = {"": "tutte", "CFF": "consulenti finanziari abilitati offerta fuori sede",
            "CFA": "consulenti finanziari autonomi", "SCF": "società di consulenza"}


def _await_key(lead):
    return f"ocf_await:{lead}"


def _answer_key(lead):
    return f"ocf_captcha:{lead}"


@frappe.whitelist()
def run_ocf_search(lead_name, cognome, nome="", sezione="", wa_phone=None, sender=None,
                   wait_seconds=150, bill_client=None, bill_price=0):
    """Job lungo: apre OCF, manda il captcha all'operatore, attende la soluzione,
    completa la ricerca e restituisce i risultati su WhatsApp."""
    from thanatos_intel.ingest.wa_bot import _wa_doc, send_text, send_image
    wa_doc = _wa_doc(wa_phone) if wa_phone else None

    def reply(body):
        if wa_doc and sender:
            send_text(wa_doc, sender, body, lead_name)

    sez = (sezione or "").upper()
    if sez not in _SEZIONI:
        sez = ""

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        reply("⚠️ Ricerca albo non disponibile (motore browser assente).")
        return {"ok": False, "reason": "playwright missing"}

    frappe.cache().set_value(_await_key(lead_name), "1", expires_in_sec=wait_seconds + 60)
    frappe.cache().delete_value(_answer_key(lead_name))

    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        try:
            pg = br.new_page()
            pg.goto(OCF_URL, wait_until="networkidle", timeout=45000)
            pg.fill("#cognome", (cognome or "").upper())
            if nome:
                pg.fill("#nome", nome.upper())
            if sez:
                try:
                    pg.select_option("#sezione_albo", sez, timeout=3000)
                except Exception:
                    pass
            png = pg.locator("#captchaImg").screenshot()

            if wa_doc and sender:
                send_image(wa_doc, sender, png,
                           f"🔐 Albo OCF — ricerca «{cognome} {nome}».\n"
                           "Scrivi il CODICE del captcha per completare la ricerca.",
                           lead_name)
            else:
                return {"ok": False, "reason": "no wa channel"}

            # attende la soluzione dell'operatore (scritta via handle_operator_message)
            sol = None
            deadline = time.time() + wait_seconds
            while time.time() < deadline:
                v = frappe.cache().get_value(_answer_key(lead_name))
                if v:
                    sol = v.decode() if isinstance(v, bytes) else str(v)
                    break
                time.sleep(3)
            if not sol:
                reply("⏱️ Captcha scaduto. Ripeti la ricerca all'albo quando vuoi.")
                return {"ok": False, "reason": "captcha timeout"}

            pg.fill("#captchaInput", sol.strip())
            # click via JS: il submit e AJAX, evita lattesa-navigazione di Playwright
            pg.eval_on_selector("#submitRicercaConsulenteButton", "el => el.click()")
            # attende risultati o messaggio (max ~20s). I risultati OCF sono
            # una DataTable renderizzata via JS: controlla i contenitori noti.
            _SEL = ("#tableContainerBody tr, #tableContainerStorico tbody tr, "
                    "table.dataTable tbody tr, .dataTables_wrapper tbody tr")
            for _ in range(20):
                pg.wait_for_timeout(1000)
                if pg.locator(_SEL).count() > 0:
                    break
                _bt = (pg.locator("body").inner_text() or "").lower()
                if "captcha errato" in _bt or "nessun risultato" in _bt:
                    break

            body_txt = (pg.locator("body").inner_text() or "").lower()
            if "captcha errato" in body_txt:
                reply("❌ Captcha errato. Ripeti la ricerca all'albo e riprova.")
                return {"ok": False, "reason": "wrong captcha"}

            rows = pg.locator(_SEL)
            n = rows.count()
            results = []
            for i in range(min(n, 15)):
                t = (rows.nth(i).inner_text() or "").strip().replace("\n", " · ")
                if t and "nessun" not in t.lower():
                    results.append(t)
            # log diagnostico per finalizzare dal vivo se serve
            if not results:
                try:
                    tinfo = pg.evaluate(
                        "() => Array.from(document.querySelectorAll('table'))"
                        ".map(t => t.id + ':' + t.querySelectorAll('tbody tr').length)")
                    frappe.log_error(
                        f"OCF read vuoto: rows_sel={n} no_result="
                        f"{'nessun risultato' in body_txt} tables={tinfo}",
                        "OCF diag")
                except Exception:
                    pass
        finally:
            br.close()
            frappe.cache().delete_value(_await_key(lead_name))
            frappe.cache().delete_value(_answer_key(lead_name))

    label_sez = _SEZIONI.get(sez, "tutte le sezioni")
    if not results:
        reply(f"🔎 *Albo OCF* — «{cognome} {nome}» ({label_sez}): "
              f"nessun iscritto trovato.")
        _bill_ocf(bill_client, bill_price, lead_name)
        return {"ok": True, "count": 0}

    lines = [f"🔎 *Albo OCF* — «{cognome} {nome}» ({label_sez}): "
             f"{len(results)} riscontro/i", ""]
    lines += [f"• {r[:200]}" for r in results[:10]]
    if len(results) > 10:
        lines.append(f"… e altri {len(results) - 10}")
    lines.append("")
    lines.append("_Fonte: Albo OCF (organismocf.it), consultazione semi-automatica._")
    reply("\n".join(lines))
    _bill_ocf(bill_client, bill_price, lead_name)
    return {"ok": True, "count": len(results)}


def _bill_ocf(client, price, lead_name):
    """Addebita il servizio OCF al wallet cliente (no-op se free/super admin)."""
    if not client or not price:
        return
    try:
        from thanatos_intel.billing.paid_gate import charge_paid_tool
        case = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
        charge_paid_tool("albo_ocf", {"client": client, "price": price, "free": False}, case)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "OCF bill")
