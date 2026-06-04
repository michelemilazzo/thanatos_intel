import hashlib
import os

import frappe
from frappe.model.document import Document


class FileSample(Document):
    def before_save(self):
        if self.file_url and not self.sha256:
            self._compute_hashes()

    def _compute_hashes(self):
        path = frappe.get_site_path() + (self.file_url if self.file_url.startswith("/") else "/" + self.file_url)
        path = path.replace("/private/files/", "/private/files/").replace("/files/", "/public/files/")
        if not os.path.exists(path):
            return
        h256, h1, h5 = hashlib.sha256(), hashlib.sha1(), hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h256.update(chunk); h1.update(chunk); h5.update(chunk)
        self.sha256 = h256.hexdigest()
        self.sha1 = h1.hexdigest()
        self.md5 = h5.hexdigest()
        self.file_size = os.path.getsize(path)
