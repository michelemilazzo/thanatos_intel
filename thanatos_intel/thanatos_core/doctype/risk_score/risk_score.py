import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


THRESHOLDS = [
    (86, "Critical"),
    (61, "High"),
    (31, "Medium"),
    (0,  "Low"),
]


def _classify(score: int) -> str:
    for threshold, label in THRESHOLDS:
        if score >= threshold:
            return label
    return "Low"


def _build_entity(case_doc) -> dict:
    """Costruisce un dict di contesto per le Risk Rule dal caso."""
    e = {
        "case_name": case_doc.name,
        "case_type": case_doc.case_type,
        "status": case_doc.status,
        "final_verdict": case_doc.final_verdict,
        "risk_score_final": case_doc.risk_score_final or 0,
    }
    # Dati client se presente
    if case_doc.client:
        client = frappe.db.get_value(
            "Investigation Client", case_doc.client,
            ["client_type", "kyc_status", "kyb_status", "risk_level", "country"],
            as_dict=1,
        ) or {}
        e.update({
            "client_type": client.get("client_type"),
            "kyc_status": client.get("kyc_status"),
            "kyb_status": client.get("kyb_status"),
            "client_risk_level": client.get("risk_level"),
            "client_country": client.get("country"),
        })
    # Entità coinvolte
    rows = frappe.get_all(
        "Case Entity",
        filters={"parent": case_doc.name, "parenttype": "Investigation Case"},
        fields=["entity", "entity_type"],
    )
    entities = []
    for r in rows:
        ent = frappe.db.get_value(
            "Investigation Entity", r.entity,
            ["entity_name", "blacklist_ref"], as_dict=1,
        ) or {}
        entities.append({
            "entity_type": r.entity_type,
            "entity_name": ent.get("entity_name"),
            "blacklisted": bool(ent.get("blacklist_ref")),
        })
    e["entities"] = entities
    e["has_blacklisted_entity"] = any(x["blacklisted"] for x in entities)
    e["has_sanctions_hit"] = bool(frappe.db.exists(
        "Sanctions Screening", {"ddd_case": case_doc.name, "matches_found": [">", 0]}
    ))
    e["entity_count"] = len(entities)
    return e


class RiskScore(Document):
    def validate(self):
        if self.score is None:
            self.score = 0
        self.classification = _classify(self.score)

    def before_save(self):
        if not self.evaluated_at:
            self.evaluated_at = now_datetime()

    @frappe.whitelist()
    def calculate(self):
        """Ricalcola il punteggio applicando tutte le Risk Rule abilitate."""
        if not self.investigation_case:
            frappe.throw("Campo 'Case' obbligatorio per il calcolo.")

        case_doc = frappe.get_doc("Investigation Case", self.investigation_case)
        e = _build_entity(case_doc)

        rules = frappe.get_all(
            "Risk Rule",
            filters={"enabled": 1},
            fields=["name", "rule_name", "category", "score_delta", "severity",
                    "selector_expression", "match_message"],
        )

        total = 0
        matched = []
        for rule in rules:
            expr = (rule.selector_expression or "").strip()
            if not expr:
                continue
            try:
                hit = bool(eval(expr, {"__builtins__": {}}, {"e": e}))  # noqa: S307
            except Exception:
                hit = False
            if hit:
                total += rule.score_delta or 0
                matched.append({
                    "rule": rule.name,
                    "category": rule.category,
                    "score_delta": rule.score_delta,
                    "severity": rule.severity,
                    "match_message": rule.match_message or rule.rule_name,
                })

        total = max(0, min(100, total))
        self.score = total
        self.classification = _classify(total)
        self.evaluated_at = now_datetime()
        self.set("matched_rules", [])
        for m in matched:
            self.append("matched_rules", m)

        self.save()
        # aggiorna anche il campo sul caso
        frappe.db.set_value("Investigation Case", self.investigation_case,
                            "risk_score_final", total)
        return {"score": total, "classification": self.classification, "matched": len(matched)}


@frappe.whitelist()
def calculate_for_case(case_name: str) -> dict:
    """Crea o aggiorna un Risk Score per il caso e ricalcola."""
    existing = frappe.db.get_value("Risk Score", {"investigation_case": case_name}, "name")
    if existing:
        doc = frappe.get_doc("Risk Score", existing)
    else:
        doc = frappe.get_doc({
            "doctype": "Risk Score",
            "investigation_case": case_name,
        })
        doc.insert(ignore_permissions=True)
    return doc.calculate()
