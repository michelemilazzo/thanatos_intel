import hashlib
import os

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class DocumentIntake(Document):
    def before_insert(self):
        if not self.uploaded_at:
            self.uploaded_at = now_datetime()
        if not self.uploaded_by:
            self.uploaded_by = frappe.session.user

    def before_save(self):
        if self.file_url and not self.sha256:
            try:
                p = _file_path(self.file_url)
                if p and os.path.exists(p):
                    h = hashlib.sha256()
                    with open(p, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            h.update(chunk)
                    self.sha256 = h.hexdigest()
                    self.file_size = os.path.getsize(p)
            except Exception:
                pass


def _file_path(file_url: str) -> str:
    if not file_url:
        return ""
    if file_url.startswith("/private/files/"):
        return frappe.get_site_path() + file_url
    if file_url.startswith("/files/"):
        return frappe.get_site_path("public") + file_url
    if file_url.startswith("/"):
        return frappe.get_site_path() + file_url
    return ""
