"""QR code PNG on the fly (guest) — usato nei print format (es. registrazione cliente sul preventivo)."""
import io

import frappe


@frappe.whitelist(allow_guest=True)
def png(data: str, box_size: int = 5):
    import qrcode
    q = qrcode.QRCode(border=1, box_size=min(int(box_size), 12))
    q.add_data(data[:512])
    q.make(fit=True)
    img = q.make_image(fill_color="#0D1B3E", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    frappe.local.response.filename = "qr.png"
    frappe.local.response.filecontent = buf.getvalue()
    frappe.local.response.type = "binary"
