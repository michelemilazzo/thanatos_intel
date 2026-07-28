"""Allineamento News e Servizi Thanatos → Pagina Facebook / Instagram.

- News: quando un News Article va live (``published`` 0→1) crea un Facebook Post
  e lo pubblica. Solo news in evidenza/interne salvo override, per non intasare
  la Pagina col firehose RSS.
- Servizi: scheduler settimanale che pubblica a rotazione un servizio attivo.

Ogni pubblicazione è resa **visiva**: se il contenuto non ha già una copertina,
viene generata una card brandizzata Thanatos (1080×1080), così il post esce come
foto e può essere pubblicato anche su Instagram (che richiede un'immagine).

Il job giornaliero delle news usa ``frappe.db.set_value`` (che NON fa scattare i
doc_events), perciò l'auto-pubblicazione è coperta sia dall'hook ``on_update``
(pubblicazioni manuali) sia dallo scheduler ``sync_published_news`` (job
giornaliero). Entrambi deduplicano sull'esistenza del Facebook Post di origine.
"""

import hashlib
import re

import frappe
from frappe.utils import add_to_date, cint, get_url, now_datetime

from thanatos_intel.integrations import facebook_graph as fb


def _settings():
    if frappe.db.exists("DocType", "Facebook Settings"):
        return frappe.get_single("Facebook Settings")
    return None


def _hashtags(s, default="") -> str:
    return (getattr(s, "social_hashtags", "") or "").strip() or default


def _abs_url(file_url: str) -> str:
    if not file_url:
        return ""
    if file_url.startswith("http://") or file_url.startswith("https://"):
        return file_url
    return get_url().rstrip("/") + "/" + file_url.lstrip("/")


def _already_posted(doctype: str, name: str) -> bool:
    return bool(frappe.db.exists(
        "Facebook Post", {"source_doctype": doctype, "source_name": name}))


def _clean(text: str) -> str:
    """Rimuove HTML e normalizza gli spazi."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _clip(text: str, n: int) -> str:
    """Taglia al confine di parola aggiungendo un'ellissi."""
    text = (text or "").strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0].rstrip(",.;:—- ")
    return (cut or text[:n]) + "…"


# ---------------------------------------------------------------------------
# Multilingua — didascalie bilingui (IT + lingue extra). Le parti fisse sono
# curate per lingua; nome/descrizione servizio e titolo/corpo news vengono
# tradotti a runtime da LibreTranslate (con cache e fallback all'originale).
# ---------------------------------------------------------------------------

_STRINGS = {
    "it": {
        "svc_price": "💶 A partire da {p} {c}",
        "svc_cta": "📩 Contattaci in privato o su WhatsApp per una consulenza riservata.",
        "svc_link": "🔗 {u}/servizi",
        "svc_tags": "#Thanatos #Investigazioni #Sicurezza",
        "news_link": "🔗 Leggi l'articolo: {u}",
        "news_tags": "#Thanatos #Investigazioni #OSINT",
    },
    "en": {
        "svc_price": "💶 Starting from {p} {c}",
        "svc_cta": "📩 Contact us privately or on WhatsApp for a confidential consultation.",
        "svc_link": "🔗 {u}/servizi",
        "svc_tags": "#Thanatos #Investigations #Security",
        "news_link": "🔗 Read the article: {u}",
        "news_tags": "#Thanatos #Investigations #OSINT",
    },
    "es": {
        "svc_price": "💶 Desde {p} {c}",
        "svc_cta": "📩 Contáctanos en privado o por WhatsApp para una consulta confidencial.",
        "svc_link": "🔗 {u}/servizi",
        "svc_tags": "#Thanatos #Investigaciones #Seguridad",
        "news_link": "🔗 Lee el artículo: {u}",
        "news_tags": "#Thanatos #Investigaciones #OSINT",
    },
    "fr": {
        "svc_price": "💶 À partir de {p} {c}",
        "svc_cta": "📩 Contactez-nous en privé ou sur WhatsApp pour une consultation confidentielle.",
        "svc_link": "🔗 {u}/servizi",
        "svc_tags": "#Thanatos #Enquêtes #Sécurité",
        "news_link": "🔗 Lire l'article : {u}",
        "news_tags": "#Thanatos #Enquêtes #OSINT",
    },
    "de": {
        "svc_price": "💶 Ab {p} {c}",
        "svc_cta": "📩 Kontaktieren Sie uns privat oder per WhatsApp für eine vertrauliche Beratung.",
        "svc_link": "🔗 {u}/servizi",
        "svc_tags": "#Thanatos #Ermittlungen #Sicherheit",
        "news_link": "🔗 Artikel lesen: {u}",
        "news_tags": "#Thanatos #Ermittlungen #OSINT",
    },
    "ro": {
        "svc_price": "💶 De la {p} {c}",
        "svc_cta": "📩 Contactează-ne în privat sau pe WhatsApp pentru o consultație confidențială.",
        "svc_link": "🔗 {u}/servizi",
        "svc_tags": "#Thanatos #Investigații #Securitate",
        "news_link": "🔗 Citește articolul: {u}",
        "news_tags": "#Thanatos #Investigații #OSINT",
    },
}
_LANG_LABEL = {"en": "🇬🇧 English", "es": "🇪🇸 Español",
               "fr": "🇫🇷 Français", "de": "🇩🇪 Deutsch", "ro": "🇷🇴 Română"}


def _extra_langs(s=None):
    """Lingue extra oltre all'italiano per la didascalia multilingua.

    Configurabile in site_config: ``"social_extra_languages": ["en", "es"]``.
    Default: solo inglese. Ignora i codici non supportati."""
    langs = frappe.conf.get("social_extra_languages")
    if langs is None:
        langs = ["en"]
    return [l for l in langs if l in _STRINGS and l != "it"]


# Glossario curato: traduzioni professionali esatte dei nomi servizio (e termini
# ricorrenti). Ha la precedenza sulla traduzione automatica, così i titoli
# risultano corretti. Chiave = testo italiano in minuscolo.
_GLOSSARY = {
    "en": {
        # Abbonamenti e Academy
        "piano free": "Free Plan",
        "piano basic professionale": "Professional Basic Plan",
        "piano professional": "Professional Plan",
        "piano legal": "Legal Plan",
        "piano enterprise": "Enterprise Plan",
        "monitoraggio continuo azienda (mensile)": "Continuous Company Monitoring (monthly)",
        "alert truffe di settore (mensile)": "Industry Scam Alerts (monthly)",
        "newsletter premium intelligence (mensile)": "Premium Intelligence Newsletter (monthly)",
        "corso osint base": "OSINT Fundamentals Course",
        "corso antifrode professionale": "Professional Anti-Fraud Course",
        "certificazione investigatore": "Investigator Certification",
        # Analisi Documenti
        "analisi contratto": "Contract Analysis",
        "analisi fattura sospetta": "Suspicious Invoice Analysis",
        "analisi proof of funds": "Proof of Funds Analysis",
        "analisi bank guarantee / mt760": "Bank Guarantee / MT760 Analysis",
        "analisi sblc": "SBLC Analysis",
        "analisi documento identita": "ID Document Analysis",
        "analisi documento notarile": "Notarial Document Analysis",
        "analisi metadati pdf / office": "PDF / Office Metadata Analysis",
        "analisi firma digitale": "Digital Signature Analysis",
        "comparazione documenti autentici": "Authentic Document Comparison",
        # Antifrode
        "analisi schema truffa": "Scam Scheme Analysis",
        "analisi investment scam": "Investment Scam Analysis",
        "analisi trading / forex scam": "Trading / Forex Scam Analysis",
        "analisi crypto / ponzi scam": "Crypto / Ponzi Scam Analysis",
        "analisi romance scam": "Romance Scam Analysis",
        "analisi broker / intermediario": "Broker / Intermediary Analysis",
        "analisi identity theft": "Identity Theft Analysis",
        "analisi frode aziendale": "Corporate Fraud Analysis",
        "analisi phishing avanzato": "Advanced Phishing Analysis",
        "analisi rete soggetti collegati": "Linked-Parties Network Analysis",
        # Corporate Intelligence
        "uk company due diligence (kyb)": "UK Company Due Diligence (KYB)",
        "due diligence aziendale full": "Full Corporate Due Diligence",
        "verifica reputazione aziendale": "Corporate Reputation Check",
        "verifica partner commerciale": "Business Partner Check",
        "mappa gruppo societario": "Corporate Group Mapping",
        "analisi soci e amministratori": "Shareholders & Directors Analysis",
        "analisi contenziosi pubblici": "Public Litigation Analysis",
        "report affidabilita commerciale": "Commercial Reliability Report",
        "verifica fornitore internazionale": "International Supplier Check",
        "analisi beneficiari effettivi": "Beneficial Owners Analysis",
        "due diligence aziendale light": "Light Corporate Due Diligence",
        # Cyber Intelligence
        "analisi malware file": "Malware File Analysis",
        "analisi url malevolo": "Malicious URL Analysis",
        "analisi software fake": "Fake Software Analysis",
        "analisi app mobile sospetta": "Suspicious Mobile App Analysis",
        "analisi ioc completa": "Full IOC Analysis",
        "verifica software pirata aziendale": "Corporate Pirated-Software Check",
        "report cyber risk pmi": "SME Cyber Risk Report",
        "monitoraggio brand abuse (mensile)": "Brand Abuse Monitoring (monthly)",
        "audit sicurezza software": "Software Security Audit",
        "analisi estensione browser": "Browser Extension Analysis",
        # Enterprise & API
        "piattaforma white label (mensile)": "White-Label Platform (monthly)",
        "api intelligence custom (mensile)": "Custom Intelligence API (monthly)",
        "integrazione sistemi terzi": "Third-Party Systems Integration",
        "formazione team interno": "Internal Team Training",
        "consulenza cyber security (orario)": "Cyber Security Consulting (hourly)",
        "perizia tecnica per tribunale": "Technical Expert Report for Court",
        "computer forensics": "Computer Forensics",
        "bonifica ambientale aziendale": "Corporate TSCM Bug Sweep",
        "workshop investigativi full-day": "Full-Day Investigative Workshops",
        "programma affiliati investigativi (setup)": "Investigative Affiliate Program (setup)",
        # Financial Intelligence
        "tracciamento blockchain e clustering wallet": "Blockchain Tracing & Wallet Clustering",
        "analisi bilancio": "Financial Statement Analysis",
        "analisi esposizione bancaria": "Bank Exposure Analysis",
        "stima interessi passivi": "Interest Expense Estimate",
        "analisi rischio insolvenza": "Insolvency Risk Analysis",
        "analisi patrimonio aziendale": "Corporate Assets Analysis",
        "report finanziario per avvocati": "Financial Report for Lawyers",
        "report finanziario per commercialisti": "Financial Report for Accountants",
        "protezione patrimoniale preliminare": "Preliminary Asset Protection",
        "due diligence finanziaria": "Financial Due Diligence",
        "valutazione azienda (fairness opinion)": "Company Valuation (Fairness Opinion)",
        # Investigazioni Complete
        "investigazione digitale base": "Basic Digital Investigation",
        "investigazione patrimoniale": "Asset Investigation",
        "investigazione aziendale": "Corporate Investigation",
        "investigazione cyber fraud": "Cyber Fraud Investigation",
        "investigazione crypto fraud": "Crypto Fraud Investigation",
        "fascicolo legale completo": "Complete Legal Case File",
        "report investigativo certificato": "Certified Investigative Report",
        "controspionaggio aziendale": "Corporate Counter-Espionage",
        "osint investigation completa": "Full OSINT Investigation",
        "dossier per avvocato — tribunale ready": "Attorney Dossier — Court-Ready",
        # Sequestri e Confische
        "analisi preliminare provvedimento": "Preliminary Order Analysis",
        "report analisi vizi procedurali": "Procedural Flaws Analysis Report",
        "perizia valore beni sequestrati": "Seized Assets Valuation",
        "analisi provenienza lecita beni": "Lawful Asset Origin Analysis",
        "dossier completo per riesame": "Full Dossier for Review",
        "dossier esproprio contestazione indennizzo": "Expropriation Compensation Dispute Dossier",
        "supporto ricorso cedu": "ECHR Appeal Support",
        "report opposizione confisca antimafia": "Anti-Mafia Confiscation Opposition Report",
        "analisi confisca urbanistica": "Urban-Planning Confiscation Analysis",
        "monitoraggio procedimento (mensile)": "Proceedings Monitoring (monthly)",
        # Verifiche Rapide
        "verifica email breach": "Email Breach Check",
        "verifica dominio": "Domain Check",
        "verifica ip reputation": "IP Reputation Check",
        "verifica telefono": "Phone Number Check",
        "verifica username / social": "Username / Social Check",
        "verifica url sospetto": "Suspicious URL Check",
        "verifica hash file": "File Hash Check",
        "verifica wallet crypto": "Crypto Wallet Check",
        "verifica azienda base": "Basic Company Check",
        "verifica persona base": "Basic Person Check",
    },
    "ro": {
        # Abbonamenti e Academy
        "piano free": "Plan Gratuit",
        "piano basic professionale": "Plan Basic profesional",
        "piano professional": "Plan Professional",
        "piano legal": "Plan Legal",
        "piano enterprise": "Plan Enterprise",
        "monitoraggio continuo azienda (mensile)": "Monitorizare continuă companie (lunar)",
        "alert truffe di settore (mensile)": "Alerte fraude de sector (lunar)",
        "newsletter premium intelligence (mensile)": "Newsletter premium intelligence (lunar)",
        "corso osint base": "Curs OSINT de bază",
        "corso antifrode professionale": "Curs antifraudă profesional",
        "certificazione investigatore": "Certificare investigator",
        # Analisi Documenti
        "analisi contratto": "Analiză contract",
        "analisi fattura sospetta": "Analiză factură suspectă",
        "analisi proof of funds": "Analiză proof of funds",
        "analisi bank guarantee / mt760": "Analiză garanție bancară / MT760",
        "analisi sblc": "Analiză SBLC",
        "analisi documento identita": "Analiză act de identitate",
        "analisi documento notarile": "Analiză document notarial",
        "analisi metadati pdf / office": "Analiză metadate PDF / Office",
        "analisi firma digitale": "Analiză semnătură digitală",
        "comparazione documenti autentici": "Comparație documente autentice",
        # Antifrode
        "analisi schema truffa": "Analiză schemă de fraudă",
        "analisi investment scam": "Analiză investment scam",
        "analisi trading / forex scam": "Analiză trading / forex scam",
        "analisi crypto / ponzi scam": "Analiză crypto / Ponzi scam",
        "analisi romance scam": "Analiză romance scam",
        "analisi broker / intermediario": "Analiză broker / intermediar",
        "analisi identity theft": "Analiză furt de identitate",
        "analisi frode aziendale": "Analiză fraudă corporativă",
        "analisi phishing avanzato": "Analiză phishing avansat",
        "analisi rete soggetti collegati": "Analiză rețea de persoane conectate",
        # Corporate Intelligence
        "uk company due diligence (kyb)": "UK Company Due Diligence (KYB)",
        "due diligence aziendale full": "Due diligence corporativă completă",
        "verifica reputazione aziendale": "Verificare reputație companie",
        "verifica partner commerciale": "Verificare partener comercial",
        "mappa gruppo societario": "Cartografiere grup societar",
        "analisi soci e amministratori": "Analiză asociați și administratori",
        "analisi contenziosi pubblici": "Analiză litigii publice",
        "report affidabilita commerciale": "Raport fiabilitate comercială",
        "verifica fornitore internazionale": "Verificare furnizor internațional",
        "analisi beneficiari effettivi": "Analiză beneficiari reali",
        "due diligence aziendale light": "Due diligence corporativă light",
        # Cyber Intelligence
        "analisi malware file": "Analiză fișier malware",
        "analisi url malevolo": "Analiză URL malițios",
        "analisi software fake": "Analiză software fals",
        "analisi app mobile sospetta": "Analiză aplicație mobilă suspectă",
        "analisi ioc completa": "Analiză IOC completă",
        "verifica software pirata aziendale": "Verificare software piratat în companie",
        "report cyber risk pmi": "Raport risc cibernetic IMM",
        "monitoraggio brand abuse (mensile)": "Monitorizare brand abuse (lunar)",
        "audit sicurezza software": "Audit securitate software",
        "analisi estensione browser": "Analiză extensie de browser",
        # Enterprise & API
        "piattaforma white label (mensile)": "Platformă white-label (lunar)",
        "api intelligence custom (mensile)": "API intelligence custom (lunar)",
        "integrazione sistemi terzi": "Integrare sisteme terțe",
        "formazione team interno": "Instruire echipă internă",
        "consulenza cyber security (orario)": "Consultanță securitate cibernetică (pe oră)",
        "perizia tecnica per tribunale": "Expertiză tehnică pentru instanță",
        "computer forensics": "Computer forensics",
        "bonifica ambientale aziendale": "Verificare TSCM (debugging) corporativă",
        "workshop investigativi full-day": "Workshop-uri de investigație full-day",
        "programma affiliati investigativi (setup)": "Program de afiliați în investigații (setup)",
        # Financial Intelligence
        "tracciamento blockchain e clustering wallet": "Urmărire blockchain și clustering wallet",
        "analisi bilancio": "Analiză situații financiare",
        "analisi esposizione bancaria": "Analiză expunere bancară",
        "stima interessi passivi": "Estimare cheltuieli cu dobânzile",
        "analisi rischio insolvenza": "Analiză risc de insolvență",
        "analisi patrimonio aziendale": "Analiză patrimoniu al companiei",
        "report finanziario per avvocati": "Raport financiar pentru avocați",
        "report finanziario per commercialisti": "Raport financiar pentru contabili",
        "protezione patrimoniale preliminare": "Protecție patrimonială preliminară",
        "due diligence finanziaria": "Due diligence financiară",
        "valutazione azienda (fairness opinion)": "Evaluare companie (Fairness Opinion)",
        # Investigazioni Complete
        "investigazione digitale base": "Investigație digitală de bază",
        "investigazione patrimoniale": "Investigație patrimonială",
        "investigazione aziendale": "Investigație corporativă",
        "investigazione cyber fraud": "Investigație cyber fraud",
        "investigazione crypto fraud": "Investigație crypto fraud",
        "fascicolo legale completo": "Dosar juridic complet",
        "report investigativo certificato": "Raport de investigație certificat",
        "controspionaggio aziendale": "Contraspionaj corporativ",
        "osint investigation completa": "Investigație OSINT completă",
        "dossier per avvocato — tribunale ready": "Dosar pentru avocat — pregătit pentru instanță",
        # Sequestri e Confische
        "analisi preliminare provvedimento": "Analiză preliminară a măsurii",
        "report analisi vizi procedurali": "Raport analiză vicii procedurale",
        "perizia valore beni sequestrati": "Expertiză valoare bunuri sechestrate",
        "analisi provenienza lecita beni": "Analiză proveniență licită a bunurilor",
        "dossier completo per riesame": "Dosar complet pentru reexaminare",
        "dossier esproprio contestazione indennizzo": "Dosar expropriere - contestare despăgubire",
        "supporto ricorso cedu": "Suport recurs CEDO",
        "report opposizione confisca antimafia": "Raport opoziție la confiscare antimafia",
        "analisi confisca urbanistica": "Analiză confiscare urbanistică",
        "monitoraggio procedimento (mensile)": "Monitorizare procedură (lunar)",
        # Verifiche Rapide
        "verifica email breach": "Verificare email breach",
        "verifica dominio": "Verificare domeniu",
        "verifica ip reputation": "Verificare reputație IP",
        "verifica telefono": "Verificare număr de telefon",
        "verifica username / social": "Verificare username / social",
        "verifica url sospetto": "Verificare URL suspect",
        "verifica hash file": "Verificare hash fișier",
        "verifica wallet crypto": "Verificare wallet crypto",
        "verifica azienda base": "Verificare companie de bază",
        "verifica persona base": "Verificare persoană de bază",
    },
}


def _lt_url():
    return (frappe.conf.get("libretranslate_url")
            or "http://10.10.0.4:5000").rstrip("/")


def _translate(text: str, lang: str) -> str:
    """Traduce it→lang via LibreTranslate, con cache Redis (30gg). Best-effort:
    su qualsiasi errore restituisce il testo originale (mai blocca la pubblicazione)."""
    text = (text or "").strip()
    if not text or lang == "it":
        return text
    # 1) glossario curato: traduzione professionale esatta (precede l'automatica)
    curated = _GLOSSARY.get(lang, {}).get(text.lower())
    if curated:
        return curated
    key = "social_tr:%s:%s" % (lang, hashlib.md5(text.encode("utf-8")).hexdigest())
    cache = None
    try:
        cache = frappe.cache()
        hit = cache.get_value(key)
        if hit:
            return hit
    except Exception:
        pass
    out = text
    try:
        import requests
        r = requests.post(_lt_url() + "/translate",
                          json={"q": text, "source": "it", "target": lang},
                          timeout=10)
        out = ((r.json() or {}).get("translatedText") or "").strip() or text
    except Exception:
        frappe.log_error(frappe.get_traceback(), "social translate")
        out = text
    try:
        if cache and out:
            cache.set_value(key, out, expires_in_sec=60 * 60 * 24 * 30)
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Card brandizzata (fallback immagine → abilita Instagram anche per testo/link)
# ---------------------------------------------------------------------------

def _brand_card(kicker: str, title: str, subtitle: str = "") -> str:
    """Genera una card 1080×1080 brandizzata Thanatos, la salva come File
    pubblico e ne restituisce l'URL assoluto (fetchabile da Meta). Best-effort:
    su qualsiasi errore ritorna "" e il chiamante ripiega sul post Link."""
    try:
        import hashlib
        import io

        from PIL import Image, ImageDraw, ImageFont

        W = H = 1080
        BG = (11, 31, 51)        # navy #0B1F33
        PANEL = (30, 52, 78)
        GOLD = (201, 162, 75)    # #C9A24B
        WHITE = (240, 244, 250)
        GREY = (150, 165, 185)
        FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
        margin = 96

        def font(sz, bold=True):
            f = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
            return ImageFont.truetype(FONT_DIR + f, sz)

        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([30, 30, W - 30, H - 30], outline=PANEL, width=2)

        def wrap(text, fnt, maxw):
            lines, cur = [], ""
            for w in (text or "").split():
                t = (cur + " " + w).strip()
                if d.textlength(t, font=fnt) <= maxw or not cur:
                    cur = t
                else:
                    lines.append(cur)
                    cur = w
            if cur:
                lines.append(cur)
            return lines

        # kicker + filetto oro
        d.text((margin, 150), (kicker or "").upper(), font=font(34), fill=GOLD)
        d.line([(margin, 208), (margin + 130, 208)], fill=GOLD, width=4)

        # titolo: wrap + auto-riduzione per stare nel riquadro
        maxw = W - 2 * margin
        size, lines, lh, tf = 88, [], 0, None
        while size >= 42:
            tf = font(size)
            lines = wrap(title, tf, maxw)
            lh = int(size * 1.16)
            if len(lines) <= 5 and len(lines) * lh <= 470:
                break
            size -= 6
        y = 268
        for ln in lines[:5]:
            d.text((margin, y), ln, font=tf, fill=WHITE)
            y += lh

        # sottotitolo (prezzo o snippet)
        if subtitle:
            sf = font(42, bold=False)
            for ln in wrap(subtitle, sf, maxw)[:2]:
                y += 12
                d.text((margin, y), ln, font=sf, fill=GREY)
                y += int(42 * 1.2)

        # footer
        d.text((margin, H - 156), "THANATOS INVESTIGAZIONI", font=font(30), fill=WHITE)
        d.text((margin, H - 112), "thanatos.agency", font=font(28, bold=False), fill=GOLD)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()

        h = hashlib.sha1(("|".join((kicker, title, subtitle))).encode("utf-8")).hexdigest()[:12]
        fname = f"social_card_{h}.png"
        existing = frappe.db.get_value("File", {"file_name": fname, "is_private": 0}, "file_url")
        if existing:
            return _abs_url(existing)
        f = frappe.get_doc({
            "doctype": "File", "file_name": fname, "is_private": 0, "content": data,
        }).insert(ignore_permissions=True)
        return _abs_url(f.file_url)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "social brand card")
        return ""


def _make_post(post_title, message, link, image_url, source_doctype, source_name, s):
    """Crea e pubblica un Facebook Post. Con immagine → post Foto (+ Instagram se
    disponibile); senza → post Link."""
    also_ig = bool(image_url and cint(getattr(s, "also_instagram", 0))
                   and fb.instagram_available())
    post = frappe.get_doc({
        "doctype": "Facebook Post",
        "post_title": (post_title or source_name)[:140],
        "post_type": "Foto" if image_url else "Link",
        "message": message,
        "link": link,
        "image_url": image_url or "",
        "also_instagram": 1 if also_ig else 0,
        "source_doctype": source_doctype,
        "source_name": source_name,
    })
    post.insert(ignore_permissions=True)
    post.publish_now()
    return post


# ---------------------------------------------------------------------------
# NEWS → social
# ---------------------------------------------------------------------------

def _news_url(doc) -> str:
    route = (doc.get("route") or "").strip("/")
    if not route:
        slug = (doc.get("slug") or "").strip("/")
        route = f"news/{slug}" if slug else ""
    base = get_url().rstrip("/")
    return f"{base}/{route}" if route else base


def _news_caption_lang(doc, s, lang) -> str:
    st = _STRINGS[lang]
    title = (doc.get("title") or "").strip()
    body = _clean(doc.get("thanatos_angle") or doc.get("excerpt") or "")
    if lang != "it":
        title = _translate(title, lang)
        if body:
            body = _translate(_clip(body, 350), lang)
    parts = [f"📰 {title}".strip()]
    if body:
        parts.append(_clip(body, 380))
    parts.append(st["news_link"].format(u=_news_url(doc)))
    parts.append(_hashtags(s, st["news_tags"]) if lang == "it" else st["news_tags"])
    return "\n\n".join(p for p in parts if p).strip()


def _news_caption(doc, s) -> str:
    """Didascalia bilingue: blocco italiano + un blocco per ogni lingua extra."""
    blocks = [_news_caption_lang(doc, s, "it")]
    for lang in _extra_langs(s):
        blocks.append("— %s —\n\n%s" % (_LANG_LABEL.get(lang, lang.upper()),
                                        _news_caption_lang(doc, s, lang)))
    return "\n\n".join(blocks).strip()


def _skip_news(doc_or_row, s) -> bool:
    """True se la news NON va pubblicata sui social (filtro anti-spam RSS)."""
    is_rss = doc_or_row.get("source_type") == "RSS Ingestion"
    if is_rss and not cint(doc_or_row.get("featured")) and not cint(
            getattr(s, "auto_publish_news_all", 0)):
        return True
    return False


def _create_and_publish_from_news(doc, s):
    title = (doc.get("title") or doc.name)
    image_url = _abs_url((doc.get("featured_image") or "").strip())
    if not image_url:
        # nessuna copertina: genera una card così il post è visivo e va su IG
        image_url = _brand_card("News", title, _clip(
            _clean(doc.get("excerpt") or doc.get("thanatos_angle") or ""), 90))
    post = _make_post(
        "News: " + title, _news_caption(doc, s), _news_url(doc),
        image_url, "News Article", doc.name, s)
    return post.name


def on_news_article_update(doc, method=None):
    """doc_event ``on_update``: pubblica sui social alla transizione 0→1 di
    ``published`` (pubblicazione manuale). Best-effort, non blocca il salvataggio.
    """
    try:
        if not cint(doc.get("published")):
            return
        before = doc.get_doc_before_save()
        if before and cint(before.get("published")):
            return  # era già pubblicato: nessuna transizione
        s = _settings()
        if not s or not fb.is_enabled() or not cint(getattr(s, "auto_publish_news", 0)):
            return
        if _skip_news(doc, s) or _already_posted("News Article", doc.name):
            return
        _create_and_publish_from_news(doc, s)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "social on_news_article_update")


def sync_published_news():
    """Scheduler: intercetta le news pubblicate dal job giornaliero (db.set_value,
    che non fa scattare gli hook) e le posta sui social. Cap di sicurezza per run.
    """
    s = _settings()
    if not s or not fb.is_enabled() or not cint(getattr(s, "auto_publish_news", 0)):
        return
    since = add_to_date(now_datetime(), hours=-30)
    rows = frappe.get_all(
        "News Article",
        filters={"published": 1, "published_at": [">=", since]},
        fields=["name", "source_type", "featured"],
        order_by="published_at desc", limit=40,
    )
    done = 0
    for r in rows:
        if done >= 8:  # non intasare la Pagina in un solo giro
            break
        if _already_posted("News Article", r.name) or _skip_news(r, s):
            continue
        try:
            doc = frappe.get_doc("News Article", r.name)
            _create_and_publish_from_news(doc, s)
            done += 1
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), f"sync_published_news {r.name}")


# ---------------------------------------------------------------------------
# SERVIZI → spotlight settimanale a rotazione
# ---------------------------------------------------------------------------

def _service_price(svc) -> str:
    price = svc.get("price")
    if price and int(price) > 0:
        return f"A partire da {int(price)} {svc.get('currency') or 'EUR'}"
    return ""


def _service_caption_lang(svc, s, lang) -> str:
    st = _STRINGS[lang]
    name = svc.get("service_name") or svc.name
    desc = _clean(svc.get("description") or "")
    if lang != "it":
        name = _translate(name, lang)
        if desc:
            desc = _translate(_clip(desc, 300), lang)
    parts = [f"🔎 {name}"]
    if desc:
        parts.append(_clip(desc, 320))
    price = svc.get("price")
    if price and int(price) > 0:
        parts.append(st["svc_price"].format(p=int(price), c=svc.get("currency") or "EUR"))
    parts.append(st["svc_cta"])
    parts.append(st["svc_link"].format(u=get_url().rstrip("/")))
    parts.append(_hashtags(s, st["svc_tags"]) if lang == "it" else st["svc_tags"])
    return "\n\n".join(p for p in parts if p).strip()


def _service_caption(svc, s) -> str:
    """Didascalia bilingue: blocco italiano + un blocco per ogni lingua extra."""
    blocks = [_service_caption_lang(svc, s, "it")]
    for lang in _extra_langs(s):
        blocks.append("— %s —\n\n%s" % (_LANG_LABEL.get(lang, lang.upper()),
                                        _service_caption_lang(svc, s, lang)))
    return "\n\n".join(blocks).strip()


def _service_image(svc) -> str:
    """Copertina del servizio se presente (vari nomi campo possibili), altrimenti
    una card brandizzata generata al volo."""
    for fld in ("image", "cover_image", "featured_image", "banner"):
        u = _abs_url((svc.get(fld) or "").strip()) if svc.get(fld) else ""
        if u:
            return u
    name = svc.get("service_name") or svc.name
    return _brand_card("Servizio Thanatos", name, _service_price(svc)
                       or _clip(_clean(svc.get("description") or ""), 90))


def _next_service(s):
    rows = frappe.get_all("Service Catalog", filters={"is_active": 1},
                          fields=["name"], order_by="creation asc")
    if not rows:
        return None
    names = [r.name for r in rows]
    last = getattr(s, "service_spotlight_last", None)
    idx = (names.index(last) + 1) % len(names) if last in names else 0
    return frappe.get_doc("Service Catalog", names[idx])


def _publish_service(svc, s):
    return _make_post(
        "Servizio: " + (svc.get("service_name") or svc.name),
        _service_caption(svc, s), get_url().rstrip("/") + "/servizi",
        _service_image(svc), "Service Catalog", svc.name, s)


def publish_service_spotlight():
    """Scheduler settimanale: pubblica a rotazione un servizio attivo."""
    try:
        s = _settings()
        if not s or not fb.is_enabled() or not cint(
                getattr(s, "service_spotlight_enabled", 0)):
            return
        svc = _next_service(s)
        if not svc:
            return
        _publish_service(svc, s)
        frappe.db.set_single_value("Facebook Settings", "service_spotlight_last", svc.name)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "social service_spotlight")


@frappe.whitelist()
def publish_service_now(service_code: str):
    """Pubblica manualmente un servizio specifico (usabile da pulsante/API)."""
    s = _settings()
    if not s or not fb.is_enabled():
        frappe.throw("Integrazione Facebook non attiva.")
    svc = frappe.get_doc("Service Catalog", service_code)
    post = _publish_service(svc, s)
    return {"name": post.name, "status": post.status, "fb_post_id": post.fb_post_id}
