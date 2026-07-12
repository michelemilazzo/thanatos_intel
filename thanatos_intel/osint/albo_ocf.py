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
                # use_local_cache=False: senza, get_value cacha il None in-process
                # (frappe.local.cache) e il worker in polling non rileggerebbe MAI
                # da Redis la risposta scritta dal processo web -> timeout perenne.
                v = frappe.cache().get_value(_answer_key(lead_name), use_local_cache=False)
                if v:
                    sol = v.decode() if isinstance(v, bytes) else str(v)
                    break
                time.sleep(3)
            if not sol:
                reply("⏱️ Captcha scaduto. Ripeti la ricerca all'albo quando vuoi.")
                return {"ok": False, "reason": "captcha timeout"}

            pg.fill("#captchaInput", sol.strip())
            # click via JS: il submit è AJAX, evita l'attesa-navigazione di Playwright
            pg.eval_on_selector("#submitRicercaConsulenteButton", "el => el.click()")
            # attende i risultati: DataTable JS id #resultTable (mappato 2026-07-12)
            _SEL = ("#resultTable tbody tr, table.dataTable tbody tr, "
                    ".dataTables_wrapper tbody tr, #tableContainerBody tr")
            for _ in range(20):
                pg.wait_for_timeout(1000)
                if pg.locator(_SEL).count() > 0:
                    break
                _bt = (pg.locator("body").inner_text() or "").lower()
                if ("captcha errato" in _bt or "codice errato" in _bt
                        or "nessun risultato" in _bt):
                    break

            body_txt = (pg.locator("body").inner_text() or "").lower()
            if "captcha errato" in body_txt or "codice errato" in body_txt:
                reply("❌ Captcha errato. Ripeti la ricerca all'albo e riprova.")
                return {"ok": False, "reason": "wrong captcha"}

            rows = pg.locator("#resultTable tbody tr")
            if rows.count() == 0:
                rows = pg.locator(_SEL)
            n = rows.count()
            results = []
            for i in range(min(n, 15)):
                cells = rows.nth(i).locator("td")
                cv = [(cells.nth(j).inner_text() or "").strip()
                      for j in range(cells.count())]
                if not cv or all(not c for c in cv):
                    continue
                if "nessun" in " ".join(cv).lower():
                    continue
                # colonne OCF: nome · indirizzo · sezione · stato · [Dettaglio]
                results.append({
                    "nome": cv[0] if len(cv) > 0 else "",
                    "indirizzo": cv[1] if len(cv) > 1 else "",
                    "sezione": cv[2] if len(cv) > 2 else "",
                    "stato": cv[3] if len(cv) > 3 else "",
                })
            if not results:
                try:
                    tinfo = pg.evaluate(
                        "() => Array.from(document.querySelectorAll('table'))"
                        ".map(t => t.id + ':' + t.querySelectorAll('tbody tr').length)")
                    frappe.log_error(
                        f"OCF read vuoto: rows_sel={n} tables={tinfo}", "OCF diag")
                except Exception:
                    pass
        finally:
            br.close()
            frappe.cache().delete_value(_await_key(lead_name))
            frappe.cache().delete_value(_answer_key(lead_name))

    label_sez = _SEZIONI.get(sez, "tutte le sezioni")
    _case = frappe.db.get_value("Intel Lead", lead_name, "linked_case") if lead_name else None
    _target = f"{cognome} {nome}".strip()
    from thanatos_intel.osint.engine import record_lookup, prior_sightings_wa
    # avvistamenti cross-caso PRIMA di registrare questa ricerca (no auto-match)
    _sight = prior_sightings_wa(_target, exclude_case=_case)

    if not results:
        record_lookup("Person", _target,
                      {"source": "albo_ocf", "count": 0, "sezione": label_sez}, case=_case)
        body = (f"🔎 *Albo OCF* — «{cognome} {nome}» ({label_sez}): "
                f"nessun iscritto trovato.")
        if _sight:
            body += "\n\n" + _sight
        reply(body)
        _bill_ocf(bill_client, bill_price, lead_name)
        return {"ok": True, "count": 0}

    record_lookup("Person", _target,
                  {"source": "albo_ocf", "count": len(results),
                   "sezione": label_sez, "results": results}, case=_case)
    body = _format_ocf_results(cognome, nome, label_sez, results)
    if _sight:
        body = _sight + "\n\n" + body
    reply(body)
    _bill_ocf(bill_client, bill_price, lead_name)
    return {"ok": True, "count": len(results)}


def _format_ocf_results(cognome, nome, label_sez, results):
    """Formatta i risultati OCF per WhatsApp: nome, stato, indirizzo + Google Maps."""
    from urllib.parse import quote
    q = f"{cognome} {nome}".strip()
    lines = [f"🔎 *Albo OCF* — «{q}» ({label_sez}): {len(results)} riscontro/i", ""]
    show = results[:10]
    with_maps = len(show) <= 6  # link mappe solo per ricerche mirate
    for r in show:
        nm = r.get("nome") or "—"
        st = r.get("stato") or ""
        line = f"• *{nm}*" + (f" — {st}" if st else "")
        ind = (r.get("indirizzo") or "").strip()
        if ind and ind.upper().replace(" ", "").rstrip(".") not in ("ND", "N.D"):
            line += f"\n   📍 {ind}"
            if with_maps:
                line += ("\n   🗺️ https://www.google.com/maps/search/"
                         f"?api=1&query={quote(ind)}")
        sez = (r.get("sezione") or "").strip()
        if sez:
            line += f"\n   _{sez.title()}_"
        lines.append(line)
    if len(results) > 10:
        lines.append(f"… e altri {len(results) - 10}. "
                     "Restringi col nome per risultati precisi.")
    lines.append("")
    lines.append("_Fonte: Albo OCF (organismocf.it), consultazione semi-automatica._")
    return "\n".join(lines)


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
