"""Marketplace dati a consumo (openapi.it) — recommender AI + listino con markup.

L'AI/recommender propone SOLO i servizi utili al caso, con prezzo (markup a catena
MMOS→Thanatos), e produce un preventivo. L'esecuzione effettiva delle API richiede il
token openapi (site_config: openapi_token) e avviene dopo il pagamento (Stripe/wallet).
Markup configurabili: openapi_markup_mmos (def 1.0=100%), openapi_markup_thanatos (def 1.0).
"""
import frappe

# Catalogo servizi (costo openapi indicativo in EUR; codici/endpoint reali da rifinire col token).
CATALOG = {
    "VISURA_ORD": {"name": "Visura camerale ordinaria", "applies": "company", "cost": 3.00,
                   "info": "stato, sede, capitale, amministratori, soci, oggetto, procedure"},
    "BILANCIO": {"name": "Bilancio depositato (XBRL)", "applies": "company", "cost": 2.75,
                 "info": "ultimo bilancio: ricavi, utile, patrimonio, debiti"},
    "TITOLARE_EFF": {"name": "Titolare effettivo (UBO)", "applies": "company", "cost": 4.00,
                     "info": "beneficiari effettivi (accesso ristretto 2026: legittimo interesse)"},
    "PROTESTI": {"name": "Protesti", "applies": "both", "cost": 1.50,
                 "info": "protesti cambiari a carico di impresa/persona"},
    "PERSONA_CARICHE": {"name": "Report persona (cariche e partecipazioni)", "applies": "person", "cost": 2.00,
                        "info": "cariche, partecipazioni e società collegate di una persona"},
    "PIVA": {"name": "Verifica P.IVA", "applies": "company", "cost": 0.05,
             "info": "validità/attività della partita IVA"},
    "CATASTO": {"name": "Visura catastale", "applies": "asset", "cost": 0.90,
                "info": "immobili e dati catastali per soggetto"},
}


def _markups():
    return (float(frappe.conf.get("openapi_markup_mmos") or 1.0),
            float(frappe.conf.get("openapi_markup_thanatos") or 1.0))


def _price(cost):
    mm, th = _markups()
    mmos = cost * (1 + mm)
    return round(mmos * (1 + th), 2)


def _core(name):
    n = (name or "").lower()
    return any(k in n for k in ("bomax", "trading hu", "worldmart", "b-consulting", "b consulting",
                                "im.e.e", "grube", "fattorelli", "conte", "venosa", "romano", "zhao"))


@frappe.whitelist()
def suggerisci_servizi(case):
    """Suggerisce i servizi dati UTILI al caso (per parte) con prezzo. Selettivo:
    priorità alle parti centrali (cedente, cessionari/gruppo, intermediari, asseveratori)."""
    c = frappe.get_doc("Investigation Case", case)
    voci = []
    for ce in (c.get("case_entities") or []):
        et = frappe.db.get_value("Investigation Entity", ce.entity, ["full_name", "entity_type"], as_dict=True)
        if not et:
            continue
        prio = _core(et.full_name)
        if et.entity_type == "Company":
            servizi = ["VISURA_ORD", "BILANCIO", "TITOLARE_EFF"]
        elif et.entity_type == "Person":
            servizi = ["PERSONA_CARICHE", "PROTESTI"] if prio else []
        else:
            servizi = []
        for s in servizi:
            voci.append({"parte": et.full_name, "tipo": et.entity_type, "servizio": s,
                         "nome": CATALOG[s]["name"], "info": CATALOG[s]["info"],
                         "prezzo": _price(CATALOG[s]["cost"]), "priorita": "alta" if prio else "bassa"})
    # raccomandati = priorità alta (ciò che serve davvero ora)
    racc = [v for v in voci if v["priorita"] == "alta"]
    tot_racc = round(sum(v["prezzo"] for v in racc), 2)
    tot_all = round(sum(v["prezzo"] for v in voci), 2)
    return {"ok": True, "raccomandati": racc, "tutti": voci,
            "totale_raccomandato": tot_racc, "totale_completo": tot_all,
            "token_attivo": bool(frappe.conf.get("openapi_token"))}


@frappe.whitelist()
def preventivo_servizi(case, registra=1):
    """Genera il testo del preventivo dei servizi dati raccomandati e lo registra."""
    r = suggerisci_servizi(case)
    racc = r["raccomandati"]
    lines = ["🛒 PREVENTIVO VERIFICHE DATI (openapi) — solo ciò che serve al caso"]
    by = {}
    for v in racc:
        by.setdefault(v["parte"], []).append(v)
    for parte, vs in by.items():
        lines.append(f"\n• {parte}")
        for v in vs:
            lines.append(f"   - {v['nome']}: € {v['prezzo']:.2f}  ({v['info']})")
    lines.append(f"\nTOTALE raccomandato: € {r['totale_raccomandato']:.2f}")
    if not r["token_attivo"]:
        lines.append("(NB: esecuzione attiva al collegamento del token openapi + pagamento)")
    text = "\n".join(lines)
    if int(registra):
        try:
            c = frappe.get_doc("Investigation Case", case)
            c.append("case_activities", {"activity_date": frappe.utils.now_datetime(),
                     "activity_type": "Report", "description": text[:1800], "operator": frappe.session.user})
            c.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "preventivo_servizi")
    return {"ok": True, "text": text, "totale": r["totale_raccomandato"]}
