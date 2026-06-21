import json
import frappe
from frappe import _


class CallLog(frappe.model.document.Document):

    def after_insert(self):
        if self.linked_appointment and self.outcome == "Risposta":
            frappe.db.set_value("Investigation Appointment", self.linked_appointment,
                                "status", "Completato")
            frappe.db.commit()

    @frappe.whitelist()
    def start_transcription(self) -> dict:
        if not self.audio_file and not self.recording_url:
            frappe.throw(_("Carica un file audio o inserisci l'URL di registrazione prima di trascrivere."))

        if self.transcription_status == "In elaborazione":
            return {"status": "already_running"}

        # Usa recording_url come audio_file se non c'è file allegato
        if not self.audio_file and self.recording_url:
            self.db_set("audio_file", self.recording_url)

        self.db_set("transcription_status", "In elaborazione")
        frappe.db.commit()

        frappe.enqueue(
            "thanatos_intel.ingest.transcription.transcribe_call_log",
            call_log_name=self.name,
            queue="long",
            timeout=900,
            now=False,
        )
        return {"status": "queued"}

    @frappe.whitelist()
    def get_transcript_html(self) -> dict:
        if self.transcription_status != "Completato" or not self.transcript_raw:
            return {"html": "", "status": self.transcription_status}

        from thanatos_intel.ingest.transcription import render_transcript_html
        segments = json.loads(self.transcript_raw or "[]")
        html = render_transcript_html(
            segments,
            speaker_a=self.speaker_a_label or "Operatore",
            speaker_b=self.speaker_b_label or "",
        )
        return {"html": html, "status": "Completato"}

    @frappe.whitelist()
    def get_speakers(self) -> dict:
        """Voci presenti nella trascrizione + se hanno un'impronta disponibile."""
        emb = json.loads(self.speaker_embeddings or "{}")
        labels = {"A": self.speaker_a_label, "B": self.speaker_b_label}
        out = []
        for spk in sorted(emb.keys()):
            out.append({"speaker": spk, "label": labels.get(spk, ""),
                        "has_embedding": bool(emb.get(spk))})
        return {"speakers": out}

    @frappe.whitelist()
    def enroll_voice(self, speaker, label, person_type="Contatto",
                     contact=None, user=None) -> dict:
        """Etichetta una voce: salva l'impronta nel DB Voiceprint e applica il nome."""
        emb = json.loads(self.speaker_embeddings or "{}")
        vec = emb.get(speaker)
        if not vec:
            frappe.throw(frappe._("Nessuna impronta vocale per {0}").format(speaker))
        from thanatos_intel.thanatos_core.doctype.voiceprint.voiceprint import enroll
        vp = enroll(label=label, embedding=vec, person_type=person_type,
                    linked_contact=contact, linked_user=user, source_call=self.name)
        field = {"A": "speaker_a_label", "B": "speaker_b_label"}.get(speaker)
        if field:
            self.db_set(field, label)
        frappe.db.commit()
        return {"ok": True, "voiceprint": vp}
