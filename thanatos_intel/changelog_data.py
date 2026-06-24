"""Changelog Thanatos Intel — voci versionate nel repo.
Per aggiungere un aggiornamento: appendere un dict a UPDATES (data ISO YYYY-MM-DD)."""
import frappe

# area: SEO | Desk | Portale | Profilo | Fatturazione | Sicurezza | Comunicazione | Sistema
# audience: Interno | Staff | Cliente | Tutti
UPDATES = [
    {"date": "2026-06-25", "area": "Desk", "audience": "Interno", "highlight": 1,
     "title": "Pagina Aggiornamenti",
     "desc": "Nuova pagina interna in Thanatos Intel con lo storico di tutte le novità rilasciate, filtrabile per area."},
    {"date": "2026-06-25", "area": "Desk", "audience": "Staff", "highlight": 1,
     "title": "Ruoli & Utenti",
     "desc": "Pagina per definire il ruolo di ogni utente (staff o portale) con un click; imposta automaticamente il tipo utente coerente. Solo amministratori."},
    {"date": "2026-06-25", "area": "Sistema", "audience": "Staff", "highlight": 1,
     "title": "Impostazioni di sistema",
     "desc": "Hub unico con stato delle integrazioni (Google Search Console, Cloudflare, email, Stripe) e accesso rapido a tutte le impostazioni native."},
    {"date": "2026-06-25", "area": "SEO", "audience": "Staff", "highlight": 1,
     "title": "SEO & Analytics nel desk",
     "desc": "Dashboard SEO spostata nel desk Thanatos Intel: traffico reale (Cloudflare), posizioni su Google (Search Console), parole chiave trovate, contenuti e ricerche interne. Switch 7/30/90 giorni."},
    {"date": "2026-06-25", "area": "SEO", "audience": "Interno",
     "title": "Google Search Console collegato",
     "desc": "Importazione automatica delle posizioni reali da Google (query, posizione media, impression, click), aggiornamento giornaliero."},
    {"date": "2026-06-24", "area": "Profilo", "audience": "Cliente", "highlight": 1,
     "title": "Profilo cliente completo",
     "desc": "Pagina profilo a schede: contatti, indirizzi multipli (residenza/domicilio/spedizione/fatturazione), verifica identità KYC/KYB con upload documenti, società collegata (UBO/amministratore), segnalazione clienti e sicurezza (2FA)."},
    {"date": "2026-06-24", "area": "Profilo", "audience": "Interno",
     "title": "Dati cliente allineati a ERPNext",
     "desc": "I dati del profilo si sincronizzano su Customer/Address/Contact nativi, così fatture e anagrafiche sono sempre coerenti."},
    {"date": "2026-06-24", "area": "Portale", "audience": "Cliente",
     "title": "Accesso clienti sempre al portale",
     "desc": "Dopo il login i clienti atterrano sempre nell'area riservata; risolto l'errore che portava alcuni clienti a una pagina di errore."},
    {"date": "2026-06-24", "area": "Portale", "audience": "Cliente",
     "title": "Privacy e consensi GDPR",
     "desc": "Pagina privacy aggiornata con gestione dei consensi (marketing, profilazione, condivisione partner), basi giuridiche, export e cancellazione dati."},
    {"date": "2026-06-24", "area": "Portale", "audience": "Cliente",
     "title": "Ricerca nel portale",
     "desc": "Barra di ricerca limitata ai casi del cliente, ai documenti e agli articoli informativi."},
    {"date": "2026-06-24", "area": "Portale", "audience": "Tutti", "highlight": 1,
     "title": "Home e sito più leggibili",
     "desc": "Home rinnovata con logo visibile ed effetto di sfondo, navigazione riorganizzata (Soluzioni, sitemap nel footer) e testi resi pienamente leggibili su tutte le pagine pubbliche."},
    {"date": "2026-06-24", "area": "Comunicazione", "audience": "Interno",
     "title": "Webmail amministratore",
     "desc": "Risolto il caricamento della webmail e collegata la casella admin@thanatos.agency all'amministratore."},
    {"date": "2026-06-24", "area": "SEO", "audience": "Interno",
     "title": "Parole chiave SEO",
     "desc": "Aggiunte 17 parole chiave strategiche (detective privato, investigatore privato, agenzia investigativa…) e pagine dedicate per intercettarle."},
]


@frappe.whitelist()
def get_updates():
    # leggibile da tutto lo staff (System User); i Guest non arrivano alla page desk
    if frappe.session.user == "Guest":
        frappe.throw("Accesso non consentito.", frappe.PermissionError)
    items = sorted(UPDATES, key=lambda u: u.get("date", ""), reverse=True)
    areas = sorted({u.get("area", "Altro") for u in UPDATES})
    return {"updates": items, "areas": areas, "count": len(items)}
