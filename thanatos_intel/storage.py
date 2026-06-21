"""Offload automatico dei file pesanti su StorageBox (/mnt/thanatos-box).

I file restano serviti normalmente da Frappe via symlink, ma i byte vivono sul box
(5 TB) invece che sul disco del bench. Si applica ai file privati allegati ai
doctype investigativi (sempre) e a qualsiasi file privato grande (sopra soglia).
"""
import os
import shutil
import frappe

# doctype i cui allegati vanno sempre sul box (dati investigativi/pesanti)
_OFFLOAD_DOCTYPES = {
    "Call Log", "Intel Lead", "Intelligence Contact", "Investigation Case",
    "Investigation Report", "Investigation Evidence", "Chain Of Custody Event",
    "Diplomatic Eligibility Case", "Communication",
}
_BIG = 512 * 1024      # file privati generici > 512KB → box
_MIN_TARGET = 20 * 1024  # per i doctype target, sopra 20KB → box


def _box_root():
    return frappe.conf.get("attachments_box", "/mnt/thanatos-box/attachments")


def offload_file_to_box(doc, method=None):
    """Hook File.after_insert: sposta i file pesanti sul box + symlink."""
    try:
        if not getattr(doc, "is_private", 0) or not doc.file_url:
            return
        if "/private/files/" not in doc.file_url:
            return
        fname = os.path.basename(doc.file_url)
        local = frappe.get_site_path("private", "files", fname)
        if os.path.islink(local) or not os.path.isfile(local):
            return  # già spostato o inesistente
        size = os.path.getsize(local)
        dt = doc.attached_to_doctype or ""
        target = dt in _OFFLOAD_DOCTYPES
        if target:
            if size < _MIN_TARGET:
                return
        elif size < _BIG:
            return

        box_dir = os.path.join(_box_root(), frappe.scrub(dt or "misc"))
        os.makedirs(box_dir, exist_ok=True)
        box_path = os.path.join(box_dir, fname)
        if os.path.exists(box_path):
            box_path = os.path.join(box_dir, f"{frappe.generate_hash(length=6)}-{fname}")
        shutil.move(local, box_path)
        os.symlink(box_path, local)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "offload_file_to_box")


@frappe.whitelist()
def offload_existing(limit: int = 500):
    """Sposta sul box i file privati pesanti già esistenti (one-shot, on demand).
    Restituisce quanti file spostati e MB liberati."""
    if not frappe.has_permission("File", "write"):
        frappe.throw("Permesso negato")
    moved, freed = 0, 0
    files = frappe.get_all("File", filters={"is_private": 1},
                           fields=["name", "file_url", "attached_to_doctype"],
                           limit=int(limit))
    for f in files:
        if not f.file_url or "/private/files/" not in f.file_url:
            continue
        fname = os.path.basename(f.file_url)
        local = frappe.get_site_path("private", "files", fname)
        try:
            if os.path.islink(local) or not os.path.isfile(local):
                continue
            size = os.path.getsize(local)
            dt = f.attached_to_doctype or ""
            target = dt in _OFFLOAD_DOCTYPES
            if (target and size < _MIN_TARGET) or (not target and size < _BIG):
                continue
            box_dir = os.path.join(_box_root(), frappe.scrub(dt or "misc"))
            os.makedirs(box_dir, exist_ok=True)
            box_path = os.path.join(box_dir, fname)
            if os.path.exists(box_path):
                box_path = os.path.join(box_dir, f"{frappe.generate_hash(length=6)}-{fname}")
            shutil.move(local, box_path)
            os.symlink(box_path, local)
            moved += 1
            freed += size
        except Exception:
            frappe.log_error(frappe.get_traceback(), "offload_existing")
    return {"moved": moved, "freed_mb": round(freed / 1024 / 1024, 1)}
