import json
import frappe


class Voiceprint(frappe.model.document.Document):
    pass


def _cosine(a, b):
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def identify(embedding, threshold=0.75):
    """Confronta un embedding con il DB voiceprint. Restituisce (label, contact, score) o (None,...)."""
    best, best_score = None, 0.0
    for vp in frappe.get_all("Voiceprint", filters={"is_active": 1},
                             fields=["name", "label", "linked_contact", "embedding"]):
        if not vp.embedding:
            continue
        try:
            ref = json.loads(vp.embedding)
        except Exception:
            continue
        score = _cosine(embedding, ref)
        if score > best_score:
            best, best_score = vp, score
    if best and best_score >= threshold:
        return best.label, best.linked_contact, round(best_score, 3)
    return None, None, round(best_score, 3)


def enroll(label, embedding, person_type="Contatto", linked_contact=None,
           linked_user=None, source_call=None):
    """Registra/aggiorna una voce nel DB. Se esiste già per quel contatto/operatore, media gli embedding."""
    flt = {}
    if linked_contact:
        flt = {"linked_contact": linked_contact}
    elif linked_user:
        flt = {"linked_user": linked_user}
    existing = frappe.db.get_value("Voiceprint", flt, "name") if flt else None
    if existing:
        doc = frappe.get_doc("Voiceprint", existing)
        try:
            old = json.loads(doc.embedding or "[]")
            n = doc.sample_count or 1
            merged = [(o * n + e) / (n + 1) for o, e in zip(old, embedding)] if old else embedding
        except Exception:
            merged = embedding
            n = 0
        doc.embedding = json.dumps(merged)
        doc.sample_count = (doc.sample_count or 1) + 1
        if label:
            doc.label = label
        doc.save(ignore_permissions=True)
        return doc.name
    doc = frappe.get_doc({
        "doctype": "Voiceprint", "label": label, "person_type": person_type,
        "linked_contact": linked_contact, "linked_user": linked_user,
        "source_call": source_call, "sample_count": 1,
        "embedding": json.dumps(embedding),
    })
    doc.insert(ignore_permissions=True)
    return doc.name
