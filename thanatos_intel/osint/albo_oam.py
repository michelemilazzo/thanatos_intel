# -*- coding: utf-8 -*-
"""Ricerca AUTOMATICA nell'Albo OAM (agenti in attività finanziaria, mediatori
creditizi, agenti nei servizi di pagamento) via Playwright.

A differenza dell'OCF, OAM NON ha captcha -> ricerca completamente automatica
(nessuno step operatore). Form: /elenchi-registri/soggetti/ (campo
#RicercaIscritti_CognomeNomeDenominazione, submit #filtri-elenchi-agenti) ->
naviga a risultati.html, risultati in <ul id=elenco-ricerca-generica><li>
(h2 = «NOME | C.F. XXX», .ui-li-aside = stato). Mappato 2026-07-12.
"""
import frappe

OAM_URL = "https://www.organismo-am.it/elenchi-registri/soggetti/"
_RESULTS = "#elenco-ricerca-generica li"


@frappe.whitelist()
def run_oam_search(lead_name, query, wa_phone=None, sender=None,
                   bill_client=None, bill_price=0):
    """Job: cerca un nominativo nell'Albo OAM e restituisce i risultati su WhatsApp."""
    from thanatos_intel.ingest.wa_bot import _wa_doc, send_text
    wa_doc = _wa_doc(wa_phone) if wa_phone else None

    def reply(body):
        if wa_doc and sender:
            send_text(wa_doc, sender, body, lead_name)

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        reply("⚠️ Ricerca albo non disponibile (motore browser assente).")
        return {"ok": False, "reason": "playwright missing"}

    results, total = [], None
    with sync_playwright() as p:
        br = p.chromium.launch(headless=True)
        try:
            pg = br.new_page()
            pg.goto(OAM_URL, wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(2000)
            pg.fill("#RicercaIscritti_CognomeNomeDenominazione", (query or "").upper())
            pg.click("#filtri-elenchi-agenti", timeout=8000)
            for _ in range(25):
                pg.wait_for_timeout(1000)
                if pg.locator(_RESULTS).count() > 0:
                    break
                bt = (pg.locator("body").inner_text() or "").lower()
                if "nessun" in bt and "risultat" in bt:
                    break

            tc = pg.locator(".totale-risultati-elenchi")
            if tc.count():
                total = (tc.first.inner_text() or "").strip()
            li = pg.locator(_RESULTS)
            for i in range(min(li.count(), 15)):
                el = li.nth(i)
                h2 = (el.locator("h2").first.inner_text()
                      if el.locator("h2").count() else "").strip()
                nome, cf = h2, ""
                if "|" in h2:
                    nome, rest = h2.split("|", 1)
                    nome = nome.strip()
                    cf = rest.replace("C.F.", "").replace("c.f.", "").strip()
                stato = ""
                aside = el.locator(".ui-li-aside")
                if aside.count():
                    stato = (aside.first.inner_text() or "").strip()
                collab = ""
                for line in (el.inner_text() or "").split("\n"):
                    if "COLLABORAZIONE" in line.upper():
                        collab = line.split(":", 1)[-1].strip()
                        break
                if nome:
                    results.append({"nome": nome, "cf": cf, "stato": stato,
                                    "collaborazione": collab})
            if not results:
                try:
                    frappe.log_error(
                        f"OAM read vuoto: url={pg.url} li={li.count()} total={total}",
                        "OAM diag")
                except Exception:
                    pass
        finally:
            br.close()

    _case = frappe.db.get_value("Intel Lead", lead_name, "linked_case") if lead_name else None
    from thanatos_intel.osint.engine import record_lookup, prior_sightings_wa
    _sight = prior_sightings_wa(query, exclude_case=_case)
    record_lookup("Person", query,
                  {"source": "albo_oam", "total": total, "count": len(results),
                   "results": results}, case=_case)

    if not results:
        body = f"🔎 *Albo OAM* — «{query}»: nessun iscritto trovato."
        if _sight:
            body += "\n\n" + _sight
    else:
        body = _format_oam(query, results, total)
        if _sight:
            body = _sight + "\n\n" + body
    reply(body)
    _bill_oam(bill_client, bill_price, lead_name)
    return {"ok": True, "count": len(results)}


def _format_oam(query, results, total):
    """Formatta i risultati OAM per WhatsApp: nome, stato, CF, collaborazione."""
    head = f"🔎 *Albo OAM* (agenti/mediatori creditizi) — «{query}»: {total or len(results)} risultato/i"
    lines = [head, ""]
    for r in results[:10]:
        line = f"• *{r['nome']}*" + (f" — {r['stato']}" if r.get("stato") else "")
        if r.get("cf"):
            line += f"\n   🆔 {r['cf']}"
        if r.get("collaborazione"):
            line += f"\n   🏢 {r['collaborazione']}"
        lines.append(line)
    if len(results) > 10:
        lines.append(f"… e altri {len(results) - 10}. Restringi col nome per risultati precisi.")
    lines.append("")
    lines.append("_Fonte: Albo OAM (organismo-am.it), consultazione automatica._")
    return "\n".join(lines)


def _bill_oam(client, price, lead_name):
    """Addebita il servizio OAM al wallet cliente (no-op se free/super admin)."""
    if not client or not price:
        return
    try:
        from thanatos_intel.billing.paid_gate import charge_paid_tool
        case = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
        charge_paid_tool("albo_oam", {"client": client, "price": price, "free": False}, case)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "OAM bill")
