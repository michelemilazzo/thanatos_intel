"""
Blacklist ingest da fonti gratuite ufficiali.

Fonti bulk (schedulato giornaliero):
  - OFAC SDN (US Treasury)         https://ofac.treasury.gov/system/files/downloads/sdn.xml
  - EU Financial Sanctions          https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content
  - UN Security Council Consolidated https://scsanctions.un.org/resources/xml/en/consolidated.xml
  - OpenSanctions cache → blacklist  (già in tabOpenSanctions Cache, push hit ad alto rischio)

Fonti reattive (per lookup su soggetto specifico):
  - ICIJ Offshore Leaks DB          https://offshoreleaks.icij.org/api/search
  - GLEIF (LEI registry)            https://api.gleif.org/api/v1/lei-records
  - AbuseIPDB                       https://api.abuseipdb.com/api/v2/check  (chiave opzionale)
  - GDELT adverse media             https://api.gdeltproject.org/api/v2/doc/doc

Ogni entry in blacklist ha external_id = "SOURCE:id" per dedup.
"""
import frappe
import requests
import xml.etree.ElementTree as ET
from frappe.utils import now_datetime, today

OFAC_URL = "https://ofac.treasury.gov/system/files/downloads/sdn.xml"
EU_URL = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content"
UN_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
ICIJ_API = "https://offshoreleaks.icij.org/api/search"
GLEIF_API = "https://api.gleif.org/api/v1/lei-records"
GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"
ABUSEIPDB_API = "https://api.abuseipdb.com/api/v2/check"


# ─── CORE UPSERT ─────────────────────────────────────────────────────────────

def upsert_entry(external_id: str, entry_type: str, entry_value: str,
                 risk_level: str, source: str, reason: str,
                 source_dataset: str = "", source_url: str = "") -> str:
    """
    Inserisce o aggiorna un record Blacklist Entry.
    Usa external_id come chiave primaria di dedup.
    Ritorna il name del documento.
    """
    if not entry_value:
        return ""
    entry_value = entry_value.strip()
    if entry_type in ("Email", "Domain", "IP", "Wallet", "IBAN"):
        entry_value = entry_value.lower()
    if not entry_value:
        return ""

    existing = None
    if external_id:
        existing = frappe.db.get_value("Blacklist Entry", {"external_id": external_id}, "name")
    if not existing:
        existing = frappe.db.get_value(
            "Blacklist Entry",
            {"entry_type": entry_type, "entry_value": entry_value, "source": source},
            "name"
        )
    if existing:
        frappe.db.set_value("Blacklist Entry", existing, {
            "is_active": 1,
            "source_url": source_url or frappe.db.get_value("Blacklist Entry", existing, "source_url"),
            "source_dataset": source_dataset or frappe.db.get_value("Blacklist Entry", existing, "source_dataset"),
            "last_seen": today(),
        }, update_modified=False)
        return existing

    doc = frappe.get_doc({
        "doctype": "Blacklist Entry",
        "entry_type": entry_type,
        "entry_value": entry_value,
        "risk_level": risk_level,
        "is_active": 1,
        "verified": 1,
        "source": source,
        "source_dataset": source_dataset,
        "source_url": source_url,
        "external_id": external_id or "",
        "added_by": "Administrator",
        "reason": reason[:1000] if reason else "",
    })
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    return doc.name


# ─── OFAC SDN ────────────────────────────────────────────────────────────────

def ingest_ofac(max_entries: int = 0) -> dict:
    """
    Scarica OFAC SDN XML e inserisce in blacklist.
    Fonte: US Department of the Treasury
    URL: https://ofac.treasury.gov/system/files/downloads/sdn.xml
    """
    r = requests.get(OFAC_URL, timeout=120)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns = {"o": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"}
    # Supporta sia namespace che no-namespace
    entries = root.findall(".//sdnEntry") or root.findall(".//{*}sdnEntry")
    inserted = 0
    updated = 0
    dataset = f"OFAC SDN {today()}"
    for entry in entries:
        uid = (entry.findtext("uid") or entry.findtext("{*}uid") or "").strip()
        if not uid:
            continue
        last = (entry.findtext("lastName") or entry.findtext("{*}lastName") or "").strip()
        first = (entry.findtext("firstName") or entry.findtext("{*}firstName") or "").strip()
        sdn_type = (entry.findtext("sdnType") or entry.findtext("{*}sdnType") or "Entity").strip()
        programs = [p.text for p in (entry.findall(".//program") or entry.findall(".//{*}program")) if p.text]
        full_name = f"{first} {last}".strip() if first else last
        if not full_name:
            continue
        entry_type = "Person" if sdn_type in ("Individual",) else "Company"
        reason = f"OFAC SDN - Programmi: {', '.join(programs)}" if programs else "OFAC SDN"
        external_id = f"OFAC:{uid}"
        source_url = f"https://sanctionssearch.ofac.treas.gov/?id={uid}"
        name = upsert_entry(external_id, entry_type, full_name, "Critical",
                            "OFAC SDN", reason, dataset, source_url)
        if name:
            inserted += 1
        if max_entries and inserted >= max_entries:
            break
        if inserted % 1000 == 0:
            frappe.db.commit()
    frappe.db.commit()
    return {"source": "OFAC SDN", "inserted": inserted, "dataset": dataset}


# ─── EU FINANCIAL SANCTIONS ──────────────────────────────────────────────────

def ingest_eu_sanctions(max_entries: int = 0) -> dict:
    """
    Scarica EU Financial Sanctions XML (lista consolidata UE).
    Fonte: European Commission - Financial Sanctions Files
    URL: https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content
    """
    r = requests.get(EU_URL, timeout=120)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    subjects = root.findall(".//subject") or root.findall(".//{*}subject")
    inserted = 0
    dataset = f"EU Financial Sanctions {today()}"
    for subj in subjects:
        logical_id = (subj.findtext("logicalId") or subj.findtext("{*}logicalId") or "").strip()
        subj_type_el = subj.find(".//classificationCode") or subj.find(".//{*}classificationCode")
        subj_type_code = (subj_type_el.text if subj_type_el is not None else "E").strip()
        entry_type = "Person" if subj_type_code == "P" else "Company"
        # Nome: prima nameAlias con wholeName, altrimenti firstName+lastName
        whole = ""
        for na in (subj.findall(".//nameAlias") or subj.findall(".//{*}nameAlias")):
            wn = na.findtext("wholeName") or na.findtext("{*}wholeName") or ""
            if wn.strip():
                whole = wn.strip()
                break
        if not whole:
            fn = subj.findtext(".//firstName") or subj.findtext(".//{*}firstName") or ""
            ln = subj.findtext(".//lastName") or subj.findtext(".//{*}lastName") or ""
            whole = f"{fn} {ln}".strip()
        if not whole:
            continue
        reg_url = subj.findtext(".//publicationUrl") or subj.findtext(".//{*}publicationUrl") or ""
        regulation = subj.findtext(".//regulationNumberTitle") or subj.findtext(".//{*}regulationNumberTitle") or ""
        reason = f"EU Financial Sanctions - {regulation}" if regulation else "EU Financial Sanctions"
        external_id = f"EU:{logical_id}" if logical_id else ""
        name = upsert_entry(external_id, entry_type, whole, "Critical",
                            "EU Sanctions", reason, dataset, reg_url)
        if name:
            inserted += 1
        if max_entries and inserted >= max_entries:
            break
        if inserted % 1000 == 0:
            frappe.db.commit()
    frappe.db.commit()
    return {"source": "EU Financial Sanctions", "inserted": inserted, "dataset": dataset}


# ─── UN CONSOLIDATED ─────────────────────────────────────────────────────────

def ingest_un_consolidated(max_entries: int = 0) -> dict:
    """
    Scarica UN Security Council Consolidated Sanctions List.
    Fonte: United Nations Security Council
    URL: https://scsanctions.un.org/resources/xml/en/consolidated.xml
    """
    r = requests.get(UN_URL, timeout=120)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    inserted = 0
    dataset = f"UN Consolidated {today()}"

    def _process(section_tag, entry_type):
        nonlocal inserted
        for entry in (root.findall(f".//{section_tag}") or root.findall(f".//{{{entry_type}}}{section_tag}")):
            dataid = ""
            for tag in ("DATAID", "dataid"):
                el = entry.find(tag)
                if el is not None and el.text:
                    dataid = el.text.strip()
                    break
            parts = []
            for tag in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME",
                        "NAME_ORIGINAL_SCRIPT", "FULL_NAME"):
                el = entry.find(tag)
                if el is not None and el.text and el.text.strip():
                    parts.append(el.text.strip())
                    if tag == "FULL_NAME":
                        parts = [el.text.strip()]
                        break
            full_name = " ".join(parts).strip()
            if not full_name:
                continue
            reason = f"UN Security Council Consolidated Sanctions"
            source_url = f"https://scsanctions.un.org/fop/fop?xml=htdocs/resources/xml/en/consolidated.xml&xslt=htdocs/resources/xsl/en/consolidated.xsl"
            external_id = f"UN:{dataid}" if dataid else ""
            name = upsert_entry(external_id, entry_type, full_name, "Critical",
                                "UN Consolidated", reason, dataset, source_url)
            if name:
                inserted += 1
            if max_entries and inserted >= max_entries:
                return
            if inserted % 500 == 0:
                frappe.db.commit()

    _process("INDIVIDUAL", "Person")
    _process("ENTITY", "Company")
    frappe.db.commit()
    return {"source": "UN Consolidated", "inserted": inserted, "dataset": dataset}


# ─── OPENSANCTIONS CACHE → BLACKLIST ─────────────────────────────────────────

def push_opensanctions_hits(min_score: int = 0, limit: int = 5000) -> dict:
    """
    Legge tabOpenSanctions Cache e promuove entità con topic sanction/crime
    a Blacklist Entry. Non duplica se external_id già presente.
    """
    rows = frappe.db.sql("""
        SELECT id, name, schema_type, caption, topics, birth_date,
               nationality, source_url
        FROM `tabOpenSanctions Cache`
        WHERE topics LIKE '%sanction%' OR topics LIKE '%crime%' OR topics LIKE '%wanted%'
        LIMIT %s
    """, (limit,), as_dict=True)
    inserted = 0
    dataset = f"OpenSanctions {today()}"
    for row in rows:
        full_name = row.get("caption") or row.get("name") or ""
        if not full_name:
            continue
        schema = row.get("schema_type", "")
        entry_type = "Person" if schema in ("Person", "LegalEntity") else "Company"
        topics = row.get("topics") or ""
        if "crime" in topics or "wanted" in topics:
            risk = "Critical"
        elif "sanction" in topics:
            risk = "Critical"
        else:
            risk = "High"
        external_id = f"OS:{row['id']}"
        reason = f"OpenSanctions - Topics: {topics}"
        src_url = row.get("source_url") or f"https://www.opensanctions.org/entities/{row['id']}/"
        name = upsert_entry(external_id, entry_type, full_name, risk,
                            "OpenSanctions", reason, dataset, src_url)
        if name:
            inserted += 1
        if inserted % 1000 == 0:
            frappe.db.commit()
    frappe.db.commit()
    return {"source": "OpenSanctions", "inserted": inserted}


# ─── FONTI REATTIVE (per soggetto specifico) ─────────────────────────────────

@frappe.whitelist()
def search_icij(query: str) -> dict:
    """
    Cerca un soggetto nel database ICIJ Offshore Leaks.
    Fonte: International Consortium of Investigative Journalists
    URL: https://offshoreleaks.icij.org
    Ritorna max 10 risultati con link diretto al record.
    """
    if not query:
        return {"results": [], "source": "ICIJ Offshore Leaks"}
    try:
        r = requests.get(ICIJ_API, params={"q": query, "c": "", "j": "", "e": "", "cat": "2"},
                         timeout=15, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        frappe.log_error(f"ICIJ search error: {e}", "BlacklistIngest")
        return {"results": [], "source": "ICIJ Offshore Leaks", "error": str(e)}

    results = []
    for item in (data.get("data") or [])[:10]:
        node_id = item.get("node_id") or item.get("id", "")
        results.append({
            "name": item.get("name", ""),
            "jurisdiction": item.get("jurisdiction", ""),
            "linked_to": item.get("linked_to", ""),
            "data_from": item.get("data_from", ""),
            "node_id": node_id,
            "url": f"https://offshoreleaks.icij.org/nodes/{node_id}" if node_id else "",
            "source": "ICIJ Offshore Leaks",
        })
    return {"results": results, "source": "ICIJ Offshore Leaks",
            "total": data.get("total", len(results))}


@frappe.whitelist()
def enrich_to_blacklist_icij(query: str) -> dict:
    """Cerca su ICIJ e promuove i match a Blacklist Entry."""
    res = search_icij(query)
    added = []
    for item in res.get("results", []):
        name_val = item.get("name", "")
        if not name_val:
            continue
        external_id = f"ICIJ:{item['node_id']}" if item.get("node_id") else ""
        reason = f"ICIJ Offshore Leaks - {item.get('data_from','')} - {item.get('jurisdiction','')}"
        doc_name = upsert_entry(
            external_id, "Company", name_val, "High",
            "ICIJ Offshore Leaks", reason,
            item.get("data_from", "ICIJ"),
            item.get("url", "")
        )
        if doc_name:
            added.append(doc_name)
    frappe.db.commit()
    return {"added": added, "source": "ICIJ Offshore Leaks"}


@frappe.whitelist()
def search_gleif(company_name: str) -> dict:
    """
    Cerca un'azienda nel GLEIF LEI Registry.
    Fonte: Global Legal Entity Identifier Foundation
    URL: https://api.gleif.org
    Dati: ragione sociale, paese, stato operativo, codice LEI.
    """
    if not company_name:
        return {"results": [], "source": "GLEIF"}
    try:
        r = requests.get(GLEIF_API,
                         params={"filter[entity.legalName]": company_name, "page[size]": 5},
                         timeout=15, headers={"Accept": "application/vnd.api+json"})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        frappe.log_error(f"GLEIF error: {e}", "BlacklistIngest")
        return {"results": [], "source": "GLEIF", "error": str(e)}
    results = []
    for item in (data.get("data") or []):
        attr = item.get("attributes", {}) or {}
        entity = attr.get("entity", {}) or {}
        reg = attr.get("registration", {}) or {}
        results.append({
            "lei": item.get("id", ""),
            "legal_name": (entity.get("legalName") or {}).get("name", ""),
            "country": (entity.get("legalAddress") or {}).get("country", ""),
            "status": entity.get("status", ""),
            "registration_status": reg.get("status", ""),
            "url": f"https://search.gleif.org/#/record/{item.get('id','')}",
            "source": "GLEIF",
        })
    return {"results": results, "source": "GLEIF",
            "total": (data.get("meta") or {}).get("total", len(results))}


@frappe.whitelist()
def search_gdelt_adverse_media(subject: str, days: int = 90) -> dict:
    """
    Cerca notizie avverse su un soggetto via GDELT Project.
    Fonte: The GDELT Project  https://gdeltproject.org
    Cerca articoli contenenti fraud, scam, arrested, sanctioned, money laundering, etc.
    """
    if not subject:
        return {"articles": [], "source": "GDELT"}
    adverse_terms = "fraud OR scam OR arrested OR sanctioned OR \"money laundering\" OR corruption OR bribery OR convicted"
    query = f'"{subject}" ({adverse_terms})'
    try:
        r = requests.get(GDELT_API, params={
            "query": query,
            "mode": "artlist",
            "maxrecords": "10",
            "format": "json",
            "timespan": f"{days}d",
        }, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        frappe.log_error(f"GDELT error: {e}", "BlacklistIngest")
        return {"articles": [], "source": "GDELT", "error": str(e)}
    articles = []
    for art in (data.get("articles") or [])[:10]:
        articles.append({
            "title": art.get("title", ""),
            "url": art.get("url", ""),
            "domain": art.get("domain", ""),
            "seendate": art.get("seendate", ""),
            "language": art.get("language", ""),
            "source": "GDELT",
        })
    return {"articles": articles, "source": "GDELT",
            "total": len(data.get("articles") or [])}


@frappe.whitelist()
def check_abuseipdb(ip: str) -> dict:
    """
    Verifica un IP su AbuseIPDB.
    Fonte: AbuseIPDB  https://www.abuseipdb.com
    Chiave API da site_config: abuseipdb_api_key (opzionale - free tier 1000/day)
    """
    if not ip:
        return {"found": False, "source": "AbuseIPDB"}
    api_key = frappe.conf.get("abuseipdb_api_key", "")
    if not api_key:
        return {"found": False, "source": "AbuseIPDB", "error": "No API key configured (abuseipdb_api_key)"}
    try:
        r = requests.get(ABUSEIPDB_API,
                         params={"ipAddress": ip, "maxAgeInDays": "90", "verbose": ""},
                         headers={"Key": api_key, "Accept": "application/json"},
                         timeout=10)
        r.raise_for_status()
        data = r.json().get("data", {})
    except Exception as e:
        frappe.log_error(f"AbuseIPDB error: {e}", "BlacklistIngest")
        return {"found": False, "source": "AbuseIPDB", "error": str(e)}
    score = data.get("abuseConfidenceScore", 0)
    found = score >= 25
    if found:
        risk = "Critical" if score >= 75 else "High"
        upsert_entry(
            f"ABUSEIP:{ip}", "IP", ip, risk, "AbuseIPDB",
            f"AbuseIPDB confidence score: {score}%",
            "AbuseIPDB", f"https://www.abuseipdb.com/check/{ip}"
        )
        frappe.db.commit()
    return {
        "ip": ip,
        "found": found,
        "abuse_score": score,
        "total_reports": data.get("totalReports", 0),
        "country": data.get("countryCode", ""),
        "isp": data.get("isp", ""),
        "source": "AbuseIPDB",
        "url": f"https://www.abuseipdb.com/check/{ip}",
    }


# ─── FULL SCREEN SU SOGGETTO (chiamato da OSINT lookup) ─────────────────────

@frappe.whitelist()
def full_subject_screen(subject_name: str, subject_type: str = "Person",
                        ip: str = "", company: str = "") -> dict:
    """
    Screening completo su un soggetto:
    - ICIJ Offshore Leaks
    - GDELT adverse media
    - AbuseIPDB (se IP fornito)
    - GLEIF (se company fornita)
    - Blacklist interna

    Ritorna dict con risultati da tutte le fonti + eventuale promozione a blacklist.
    """
    out = {}
    if subject_name:
        out["icij"] = search_icij(subject_name)
        out["gdelt"] = search_gdelt_adverse_media(subject_name)
        # Controlla blacklist interna
        bl = frappe.get_all("Blacklist Entry",
                            filters={"entry_value": subject_name, "is_active": 1},
                            fields=["name", "risk_level", "source", "source_url", "reason"])
        out["internal_blacklist"] = bl
    if ip:
        out["abuseipdb"] = check_abuseipdb(ip)
    if company:
        out["gleif"] = search_gleif(company)
        out["icij_company"] = search_icij(company)
    return out


# ─── SCHEDULED JOBS ──────────────────────────────────────────────────────────

def daily_sanctions_sync():
    """
    Job giornaliero: aggiorna OFAC + EU + UN.
    Schedulato in hooks.scheduler_events.daily.
    """
    results = {}
    for fn, label in [(ingest_ofac, "OFAC"), (ingest_eu_sanctions, "EU"),
                      (ingest_un_consolidated, "UN")]:
        try:
            results[label] = fn()
        except Exception as e:
            frappe.log_error(f"{label} ingest error: {e}", "BlacklistIngest")
            results[label] = {"error": str(e)}
    # Promuovi hit OpenSanctions cache ad alto rischio
    try:
        results["OpenSanctions"] = push_opensanctions_hits()
    except Exception as e:
        frappe.log_error(f"OS push error: {e}", "BlacklistIngest")
    frappe.logger().info(f"[BlacklistIngest] daily_sanctions_sync: {results}")
    return results
