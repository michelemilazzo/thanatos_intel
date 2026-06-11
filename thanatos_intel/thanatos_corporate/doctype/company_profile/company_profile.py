import base64
import json

import frappe
import requests
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

BASE = "https://api.company-information.service.gov.uk"
MASS_REG_POSTCODES = {"EC1V 2NX", "WC2H 9JQ", "N1 7GU", "EC1A 2BN"}


def _api(path):
    key = frappe.conf.get("companies_house_api_key")
    if not key:
        frappe.throw("companies_house_api_key non configurata in site_config.")
    headers = {"Authorization": "Basic " + base64.b64encode((key + ":").encode()).decode(),
               "User-Agent": "thanatos-intel"}
    r = requests.get(BASE + path, headers=headers, timeout=25)
    r.raise_for_status()
    return r.json()


def _addr(a):
    a = a or {}
    return ", ".join(filter(None, [a.get("address_line_1"), a.get("address_line_2"),
                                   a.get("locality"), a.get("postal_code"), a.get("country")]))


class CompanyProfile(Document):

    @frappe.whitelist()
    def sync_companies_house(self):
        if not self.company_number:
            frappe.throw("Inserire il Company Number prima di sincronizzare.")
        self.populate_from_ch(self.company_number)
        self.save()
        frappe.db.commit()
        return {"company": self.company_name, "number": self.company_number,
                "status": self.current_status, "risk_score": self.risk_score,
                "officers": len(self.officers), "psc": len(self.psc)}

    def populate_from_ch(self, cn):
        c = _api(f"/company/{cn}")
        acc = c.get("accounts") or {}
        cs = c.get("confirmation_statement") or {}
        self.company_name = c.get("company_name")
        self.company_number = c.get("company_number")
        self.jurisdiction = c.get("jurisdiction") or "england-wales"
        self.company_type = c.get("type")
        self.current_status = c.get("company_status")
        self.incorporation_date = c.get("date_of_creation")
        self.dissolution_date = c.get("date_of_dissolution")
        self.registered_address = _addr(c.get("registered_office_address"))
        self.country = (c.get("registered_office_address") or {}).get("country")
        self.sic_codes = ", ".join(c.get("sic_codes") or [])
        self.accounts_overdue = 1 if acc.get("overdue") else 0
        self.accounts_next_due = acc.get("next_due")
        self.confirmation_next_due = cs.get("next_due")
        self.companies_house_url = f"https://find-and-update.company-information.service.gov.uk/company/{cn}"
        self.last_synced = now_datetime()

        # officers
        officers = _api(f"/company/{cn}/officers").get("items", [])
        try:
            psc_items = _api(f"/company/{cn}/persons-with-significant-control").get("items", [])
        except Exception:
            psc_items = []
        psc_names = {(p.get("name") or "").lower() for p in psc_items}

        self.set("officers", [])
        for o in officers:
            dob = o.get("date_of_birth") or {}
            self.append("officers", {
                "full_name": o.get("name"),
                "role": o.get("officer_role"),
                "appointed_on": o.get("appointed_on"),
                "resigned_on": o.get("resigned_on"),
                "is_psc": 1 if (o.get("name") or "").lower() in psc_names else 0,
                "dob": f"{dob.get('month','')}/{dob.get('year','')}" if dob else "",
                "nationality": o.get("nationality"),
                "country_of_residence": o.get("country_of_residence"),
                "occupation": o.get("occupation"),
                "officer_address": _addr(o.get("address")),
            })

        self.set("psc", [])
        for p in psc_items:
            self.append("psc", {
                "name_psc": p.get("name"),
                "kind": p.get("kind"),
                "nationality": p.get("nationality"),
                "natures_of_control": ", ".join(p.get("natures_of_control") or []),
                "notified_on": p.get("notified_on"),
                "ceased_on": p.get("ceased_on"),
            })

        # filing history (ultimi 15)
        try:
            fh = _api(f"/company/{cn}/filing-history?items_per_page=15").get("items", [])
        except Exception:
            fh = []
        self.set("filings", [])
        for f in fh:
            self.append("filings", {
                "filing_date": f.get("date"),
                "category": f.get("category"),
                "filing_type": f.get("type"),
                "description": f.get("description"),
            })

        # corporate links: altre cariche dei director (crea stub Company Profile)
        self.set("links", [])
        seen = set()
        for o in officers:
            link = (o.get("links", {}) or {}).get("officer", {}).get("appointments")
            if not link:
                continue
            try:
                apps = _api(link).get("items", [])
            except Exception:
                apps = []
            for a in apps:
                at = a.get("appointed_to", {}) or {}
                conum, coname = at.get("company_number"), at.get("company_name")
                if not conum or conum == cn or conum in seen:
                    continue
                seen.add(conum)
                stub = frappe.db.get_value("Company Profile", {"company_number": conum}, "name")
                if not stub:
                    sd = frappe.get_doc({"doctype": "Company Profile", "company_name": coname,
                                         "company_number": conum, "jurisdiction": "england-wales",
                                         "current_status": at.get("company_status")})
                    sd.flags.skip_ch_links = True
                    sd.insert(ignore_permissions=True)
                    stub = sd.name
                self.append("links", {"linked_company": stub, "link_type": "shared_director",
                                      "note": f"via {o.get('name')}"})

        self.raw_json = json.dumps({"company": c, "officers": officers, "psc": psc_items}, default=str)[:140000]
        self._score_risk()

    def _score_risk(self):
        score, notes = 0, []
        if self.accounts_overdue:
            score += 25; notes.append("Bilanci overdue")
        if (self.current_status or "").lower() == "dissolved":
            score += 15; notes.append("Societa sciolta")
        pc = (self.registered_address or "").upper()
        if any(p in pc for p in MASS_REG_POSTCODES):
            score += 20; notes.append("Sede mass-registration")
        try:
            if self.incorporation_date and (getdate() - getdate(self.incorporation_date)).days < 365:
                score += 10; notes.append("Neocostituita (<1 anno)")
        except Exception:
            pass
        # PSC con controllo totale = concentrazione
        if any("75-to-100" in (p.natures_of_control or "") for p in self.psc):
            score += 5; notes.append("PSC con controllo 75-100%")
        # nessun bilancio mai depositato e tipo finanziario
        if "financ" in (self.sic_codes or "").lower() and self.accounts_overdue:
            score += 10; notes.append("Finanziaria senza bilanci")
        self.risk_score = min(100, score)
        self.risk_notes = "; ".join(notes)


@frappe.whitelist()
def sync_company(company_number, investigation_case=None, entity=None):
    """Crea/aggiorna un Company Profile dai dati Companies House e lo restituisce."""
    frappe.only_for(("System Manager", "Investigation Manager", "Investigator"))
    company_number = (company_number or "").strip().upper()
    name = frappe.db.get_value("Company Profile", {"company_number": company_number}, "name")
    doc = frappe.get_doc("Company Profile", name) if name else frappe.new_doc("Company Profile")
    doc.company_number = company_number
    doc.populate_from_ch(company_number)
    if investigation_case:
        doc.investigation_case = investigation_case
    if entity:
        doc.entity = entity
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"name": doc.name, "company": doc.company_name, "status": doc.current_status,
            "risk_score": doc.risk_score, "officers": len(doc.officers),
            "psc": len(doc.psc), "links": len(doc.links)}
