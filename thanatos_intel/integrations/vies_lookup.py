"""VIES EU VAT lookup — autofill dati azienda da partita IVA.

Endpoint REST: https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{cc}/vat/{num}
Se il nodo del paese è offline (userError≠VALID/MS_MAX_CONCURRENT_REQ), usa i dati
approssimativi (viesApproximate) come fallback.
"""
import re
import requests
import frappe

_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{cc}/vat/{num}"
_TIMEOUT = 12
_CC_RE = re.compile(r"^([A-Z]{2})(.+)$")


def _split_vat(raw):
    raw = (raw or "").strip().upper().replace(" ", "").replace(".", "").replace("-", "")
    m = _CC_RE.match(raw)
    if m:
        return m.group(1), m.group(2)
    return None, raw


@frappe.whitelist()
def lookup(vat_number):
    """Cerca la P.IVA su VIES e restituisce i dati azienda normalizzati.
    Usato dall'Autofill nel form Investigation Client e Customer."""
    cc, num = _split_vat(vat_number)
    if not cc or len(num) < 5:
        return {"ok": False, "error": "Formato P.IVA non valido (es. IT02603150596)."}
    try:
        r = requests.get(_URL.format(cc=cc, num=num), timeout=_TIMEOUT)
        data = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Errore connessione VIES: {e}"}

    valid = data.get("isValid", False)
    err = data.get("userError", "")

    # dati preferiti: risposta piena se valida, fallback approssimativo se offline
    name = (data.get("name") or "").strip()
    address = (data.get("address") or "").strip()

    if not name or name in ("---", ""):
        approx = data.get("viesApproximate") or {}
        name = approx.get("name", "").strip() if approx.get("name") not in (None, "---") else ""
        parts = [approx.get(k, "") for k in ("street", "postalCode", "city") if approx.get(k) not in (None, "---", "")]
        address = ", ".join(p for p in parts if p)

    if not name:
        return {"ok": False, "valid": valid, "error": f"VIES: {err or 'nessun dato'}", "raw": data}

    result = _parse_address(address)
    result.update({
        "ok": True,
        "valid": valid,
        "offline": err not in ("", "VALID"),
        "vat": cc + num,
        "country_code": cc,
        "company_name": name,
        "raw_address": address,
    })
    return result


def _parse_address(address):
    """Prova a estrarre via, CAP e città dalla stringa indirizzo VIES."""
    lines = [l.strip() for l in address.replace("\n", ",").split(",") if l.strip()]
    out = {"address_line1": "", "city": "", "pincode": "", "state": ""}
    if not lines:
        return out
    out["address_line1"] = lines[0]
    # cerca CAP 5 cifre + città
    for part in lines[1:]:
        m = re.match(r"^(\d{5})\s+(.+)$", part.strip())
        if m:
            out["pincode"] = m.group(1)
            out["city"] = m.group(2).title()
        elif re.match(r"^\d{5}$", part.strip()):
            out["pincode"] = part.strip()
        else:
            if not out["city"]:
                out["city"] = part.title()
    return out
