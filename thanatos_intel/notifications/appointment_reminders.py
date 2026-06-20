"""Promemoria appuntamenti: invia email all'operatore N minuti prima."""
import frappe
from frappe.utils import now_datetime, add_to_date


def send_appointment_reminders():
    now = now_datetime()
    upcoming = frappe.db.sql("""
        SELECT name, title, appointment_type, appointment_date, appointment_time,
               assigned_to, linked_case, linked_client, location, reminder_minutes
        FROM `tabInvestigation Appointment`
        WHERE status IN ('Pianificato', 'Confermato')
          AND reminder_sent = 0
          AND appointment_date IS NOT NULL
          AND appointment_time IS NOT NULL
    """, as_dict=True)

    for appt in upcoming:
        try:
            import datetime
            appt_dt = datetime.datetime.combine(
                appt.appointment_date,
                (datetime.datetime.min + appt.appointment_time).time()
                if isinstance(appt.appointment_time, datetime.timedelta)
                else appt.appointment_time,
            )
            remind_at = appt_dt - datetime.timedelta(minutes=int(appt.reminder_minutes or 30))
            if remind_at <= now <= appt_dt:
                _send_reminder(appt)
                frappe.db.set_value("Investigation Appointment", appt.name, "reminder_sent", 1)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"appointment_reminder {appt.name}")

    frappe.db.commit()


def _send_reminder(appt: dict):
    if not appt.assigned_to:
        return
    op_email = frappe.db.get_value("User", appt.assigned_to, "email")
    if not op_email:
        return

    base_url = frappe.utils.get_url()
    case_link = ""
    if appt.linked_case:
        case_link = f"<br>Pratica: <a href='{base_url}/app/investigation-case/{appt.linked_case}'>{appt.linked_case}</a>"

    frappe.sendmail(
        recipients=[op_email],
        subject=f"[Thanatos] Promemoria: {appt.title} — {appt.appointment_date}",
        message=(
            f"<div style='font-family:sans-serif;max-width:600px'>"
            f"<p><strong>Promemoria appuntamento</strong></p>"
            f"<table style='border-collapse:collapse;width:100%'>"
            f"<tr><td style='padding:4px 8px;color:#666'>Tipo</td>"
            f"<td style='padding:4px 8px'><strong>{appt.appointment_type}</strong></td></tr>"
            f"<tr><td style='padding:4px 8px;color:#666'>Data/Ora</td>"
            f"<td style='padding:4px 8px'>{appt.appointment_date} {appt.appointment_time or ''}</td></tr>"
            f"<tr><td style='padding:4px 8px;color:#666'>Luogo</td>"
            f"<td style='padding:4px 8px'>{appt.location or '—'}</td></tr>"
            f"</table>"
            f"{case_link}"
            f"<p style='margin-top:16px'>"
            f"<a href='{base_url}/app/investigation-appointment/{appt.name}' "
            f"style='background:#C8A96E;color:#0A0E1A;padding:8px 16px;border-radius:4px;"
            f"text-decoration:none;font-weight:bold'>Apri appuntamento →</a></p>"
            f"</div>"
        ),
        delayed=False,
    )
