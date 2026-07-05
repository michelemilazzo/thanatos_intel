"""Presa in carico / trasferimento / condivisione delle pratiche (Investigation
Case) — stessa logica del Centralino chat, applicata alla struttura: il primo
investigatore che accetta prende il caso, può trasferirlo o condividerlo
aggiungendo altri operatori al team (Case Assignment)."""
import frappe
from frappe import _

from thanatos_intel.api.centralino import _is_manager, _notify_user


def _my_investigator(user=None):
    user = user or frappe.session.user
    return frappe.db.get_value("Investigator", {"platform_user": user},
                               ["name", "full_name"], as_dict=True)


def _investigator_user(inv_name):
    return frappe.db.get_value("Investigator", inv_name, "platform_user")


def _is_case_owner(case_doc, user=None):
    user = user or frappe.session.user
    if not case_doc.assigned_investigator:
        return False
    return _investigator_user(case_doc.assigned_investigator) == user


def _team_users(case_doc):
    """Email degli utenti nel team (assignments) + assegnatario."""
    users = set()
    if case_doc.assigned_investigator:
        u = _investigator_user(case_doc.assigned_investigator)
        if u:
            users.add(u)
    for row in (case_doc.case_assignments or []):
        if row.assignee_email:
            users.add(row.assignee_email)
        elif row.assignee_type == "Investigator" and row.assignee:
            u = frappe.db.get_value("Investigator", {"full_name": row.assignee},
                                    "platform_user") or _investigator_user(row.assignee)
            if u:
                users.add(u)
    return users


@frappe.whitelist()
def claim_case(case):
    """Presa in carico atomica: vince il primo investigatore che accetta."""
    user = frappe.session.user
    inv = _my_investigator(user)
    if not inv:
        frappe.throw(_("Nessun profilo Investigator collegato al tuo utente"))
    changed = frappe.db.sql("""
        UPDATE `tabInvestigation Case` SET assigned_investigator = %s
        WHERE name = %s AND (assigned_investigator IS NULL OR assigned_investigator = '')
    """, (inv.name, case))
    frappe.db.commit()
    assigned = frappe.db.get_value("Investigation Case", case, "assigned_investigator")
    if assigned == inv.name:
        _log_activity(case, f"✋ Pratica presa in carico da {inv.full_name or user}")
        return {"ok": True, "assigned_investigator": inv.name}
    holder = frappe.db.get_value("Investigator", assigned, "full_name") or assigned
    return {"ok": False, "assigned_investigator": assigned,
            "error": f"Già in carico a {holder}"}


@frappe.whitelist()
def transfer_case(case, to_user, note=""):
    """Trasferimento pratica: solo assegnatario o manager."""
    user = frappe.session.user
    doc = frappe.get_doc("Investigation Case", case)
    if doc.assigned_investigator and not _is_case_owner(doc, user) and not _is_manager(user):
        frappe.throw(_("Solo l'assegnatario o un manager può trasferire la pratica"))
    target = frappe.db.get_value("Investigator", {"platform_user": to_user},
                                 ["name", "full_name"], as_dict=True)
    if not target:
        frappe.throw(_("L'utente scelto non ha un profilo Investigator"))
    frappe.db.set_value("Investigation Case", case, "assigned_investigator", target.name)
    frappe.db.commit()
    _log_activity(case, f"↪ Pratica trasferita a {target.full_name or to_user}"
                  + (f" — {note}" if note else ""))
    _notify_user(to_user, f"↪ Pratica trasferita a te: {case} — {doc.case_title or ''}"
                 + (f" ({note})" if note else ""), case_name=case)
    return {"ok": True}


@frappe.whitelist()
def share_case(case, to_user, role_description=""):
    """Condivisione: aggiunge un operatore al team della pratica (Case Assignment)."""
    user = frappe.session.user
    doc = frappe.get_doc("Investigation Case", case)
    if doc.assigned_investigator and not _is_case_owner(doc, user) and not _is_manager(user):
        frappe.throw(_("Solo l'assegnatario o un manager può condividere la pratica"))
    if to_user in _team_users(doc):
        return {"ok": True, "already": True}
    target = frappe.db.get_value("Investigator", {"platform_user": to_user},
                                 ["name", "full_name"], as_dict=True)
    doc.append("case_assignments", {
        "assignee_type": "Investigator",
        "assignee": (target.full_name if target else to_user),
        "assignee_email": to_user,
        "role_description": role_description or "Operatore aggiunto (condivisione)",
    })
    doc.flags.ignore_mandatory = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    _log_activity(case, f"➕ Team: aggiunto {(target and target.full_name) or to_user}")
    _notify_user(to_user, f"➕ Sei stato aggiunto alla pratica {case} — {doc.case_title or ''}",
                 case_name=case)
    return {"ok": True}


@frappe.whitelist()
def case_team(case):
    """Stato team per la UI: assegnatario, membri, permessi dell'utente corrente."""
    doc = frappe.get_doc("Investigation Case", case)
    user = frappe.session.user
    holder_user = doc.assigned_investigator and _investigator_user(doc.assigned_investigator)
    return {
        "assigned_investigator": doc.assigned_investigator,
        "assigned_name": doc.assigned_investigator and frappe.db.get_value(
            "Investigator", doc.assigned_investigator, "full_name"),
        "assigned_user": holder_user,
        "team": sorted(_team_users(doc)),
        "is_mine": holder_user == user,
        "is_manager": _is_manager(user),
        "has_investigator": bool(_my_investigator(user)),
    }


def _log_activity(case, description):
    try:
        doc = frappe.get_doc("Investigation Case", case)
        doc.append("case_activities", {
            "activity_date": frappe.utils.now_datetime(),
            "activity_type": "Note",
            "description": description[:500],
            "operator": frappe.session.user,
        })
        doc.flags.ignore_mandatory = True
        doc.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "case_team _log_activity")
