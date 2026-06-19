"""Arricchimento news Thanatos: testo completo leggibile + traduzione nella
lingua del sito (libretranslate) + "Analisi Thanatos" per-tema con CTA al
servizio pertinente. Veloce e affidabile (niente LLM lento). Usato in ingestion+backfill.
"""
import re
import frappe
import requests

UA = {"User-Agent": "Mozilla/5.0 thanatos-news"}

# tema -> (regex, label CTA, url CTA, paragrafo "Analisi Thanatos")
THEMES = [
    (r"breach|leak|data breach|hack|ransomware|malware|spyware|exploit|cyber|violazione dati|attacco|vulnerabil",
     "Indagine OSINT & Cyber", "/servizi",
     "Dopo un attacco o una fuga di dati Thanatos conduce indagini OSINT e cyber per attribuire la "
     "minaccia, misurarne l'impatto e raccogliere elementi utili in sede legale."),
    (r"\bwallet\b|bitcoin|ethereum|cryptocurrency|criptovalut|usdt|on-chain|stablecoin|defi|exchange crypto",
     "Verifica un wallet sospetto", "/servizi",
     "I wallet e i flussi citati possono essere tracciati on-chain: Thanatos verifica titolarita, "
     "movimenti, collegamenti a exchange/VASP e punti di possibile recupero dei fondi."),
    (r"truffa|frode|fraud|scam|phishing|riciclagg|launder|ponzi|raggir|estorsion",
     "Apri un caso antifrode", "/servizi",
     "In casi di frode o phishing Thanatos ricostruisce le identita dietro l'inganno, raccoglie prove "
     "OSINT con valore probatorio e supporta la denuncia alle autorita."),
    (r"sanzion|ofac|sanction|blacklist|embargo|watchlist|antiricicl|aml",
     "Verifica nella blacklist", "/verifica-blacklist",
     "Thanatos verifica persone e aziende contro liste sanzioni internazionali e blacklist, "
     "per evitare rapporti con soggetti a rischio."),
    (r"scompars|missing|rapiment|kidnap|omicid|morte|incidente|indagat",
     "Indagine investigativa", "/servizi",
     "Thanatos conduce indagini investigative su persone e contesti con metodo rigoroso e catena di "
     "custodia delle prove, a supporto di legali e privati."),
    (r"azienda|company|due diligence|corporate|appalt|fornitor|partner|socio",
     "Due diligence aziendale", "/servizi",
     "Thanatos esegue due diligence su aziende, titolari effettivi e affidabilita di fornitori e "
     "partner, prima di firmare contratti o investire."),
]
DEFAULT = ("Scopri cosa puo fare Thanatos", "/servizi",
           "Thanatos affianca privati, aziende e studi legali con intelligence investigativa: OSINT, "
           "antifrode, tracciamento crypto, verifiche e due diligence.")


def _strip(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def fetch_fulltext(url):
    if not url:
        return []
    try:
        r = requests.get(url, timeout=10, headers=UA)
        if r.status_code != 200:
            return []
        html = r.text
        m = re.search(r"<article[^>]*>(.*?)</article>", html, re.I | re.S) \
            or re.search(r"<main[^>]*>(.*?)</main>", html, re.I | re.S)
        block = m.group(1) if m else html
        return [p for p in (_strip(x) for x in re.findall(r"<p[^>]*>(.*?)</p>", block, re.I | re.S))
                if len(p) > 40][:25]
    except Exception:
        return []


def _lt(text, target, source="auto"):
    text = (text or "").strip()
    if not text:
        return text
    base = frappe.conf.get("libretranslate_url") or "http://10.10.0.4:5000"
    try:
        r = requests.post(base.rstrip("/") + "/translate", timeout=20,
                          json={"q": text[:4500], "source": source, "target": target, "format": "text"})
        if r.ok:
            return (r.json() or {}).get("translatedText") or text
    except Exception:
        pass
    return text


def theme_for(text):
    t = (text or "").lower()
    for rx, label, url, angle in THEMES:
        if re.search(rx, t):
            return label, url, angle
    return DEFAULT


def enrich(title, raw_content, source_url, lang="it", source_lang="auto"):
    paras = fetch_fulltext(source_url)
    if not paras:
        raw = _strip(raw_content)
        paras = [raw[i:i+700] for i in range(0, min(len(raw), 3500), 700)] if raw else []
    full_src = " ".join(paras)
    label, url, angle = theme_for((title or "") + " " + full_src)

    need_tr = (source_lang or "auto") not in (lang, "")
    title_out = _lt(title, lang, source_lang) if need_tr else title
    paras_out = [_lt(p, lang, source_lang) for p in paras] if need_tr else paras

    body_html = "".join("<p>%s</p>" % p for p in paras_out) \
        or ("<p>%s</p>" % frappe.utils.escape_html(_strip(raw_content)))
    excerpt = _strip(" ".join(paras_out))[:280]
    return {
        "title": (title_out or title)[:240],
        "excerpt": (excerpt + ("…" if len(excerpt) >= 280 else "")) or (title_out or title),
        "body_html": body_html,
        "thanatos_angle": angle,
        "cta_label": label,
        "cta_url": url,
    }
