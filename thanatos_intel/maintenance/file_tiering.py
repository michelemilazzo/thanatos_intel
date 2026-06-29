"""File tiering: i file non acceduti da N giorni vengono spostati sul box
(StorageBox), lasciando un symlink → restano serviti ma liberano il disco locale.
Schedulato in daily_long (vedi hooks.py).
"""
import os
import shutil
import time
import frappe

BOX_ROOT = "/mnt/thanatos-box/files-tier"   # archivio file freddi sul box
IDLE_DAYS = 7
MIN_SIZE = 50 * 1024                         # sotto 50KB non vale spostare (overhead symlink/SSHFS)
SUBDIRS = ("private/files", "public/files")


def _box_ready():
    parent = os.path.dirname(BOX_ROOT)
    return os.path.isdir(parent) and os.access(parent, os.W_OK)


def tier_cold_files():
    if not _box_ready():
        frappe.logger().warning("file_tiering: box non disponibile, salto")
        return {"skipped": "box non montato"}
    site = frappe.local.site
    cutoff = time.time() - IDLE_DAYS * 86400
    moved = 0
    freed = 0
    for sub in SUBDIRS:
        base = frappe.get_site_path(*sub.split("/"))
        if not os.path.isdir(base):
            continue
        box_base = os.path.join(BOX_ROOT, site, sub)
        for root, _dirs, files in os.walk(base):
            for fn in files:
                fpath = os.path.join(root, fn)
                try:
                    if os.path.islink(fpath) or not os.path.isfile(fpath):
                        continue
                    st = os.lstat(fpath)
                    if st.st_size < MIN_SIZE:
                        continue
                    last_used = max(st.st_atime, st.st_mtime)
                    if last_used > cutoff:
                        continue  # ancora "caldo"
                    rel = os.path.relpath(fpath, base)
                    dest = os.path.join(box_base, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    if os.path.exists(dest):
                        os.remove(fpath)
                    else:
                        shutil.move(fpath, dest)
                    os.symlink(dest, fpath)
                    moved += 1
                    freed += st.st_size
                except Exception:
                    frappe.log_error(frappe.get_traceback(), "file_tiering")
    if moved:
        frappe.logger().info("file_tiering: spostati %d file (%d MB) nel box"
                             % (moved, freed // 1048576))
    return {"moved": moved, "freed_mb": freed // 1048576}
