import base64
import io
import frappe


class WhatsAppNumber(frappe.model.document.Document):

    def get_wa_url(self) -> str:
        phone = (self.phone_number or "").replace("+", "").replace(" ", "").replace("-", "")
        text = (self.wa_link_text or "").strip()
        url = f"https://wa.me/{phone}"
        if text:
            import urllib.parse
            url += "?text=" + urllib.parse.quote(text)
        return url

    @frappe.whitelist()
    def get_qr_base64(self) -> dict:
        url = self.get_wa_url()
        try:
            import qrcode
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="#0A0E1A", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            return {"url": url, "qr": f"data:image/png;base64,{b64}"}
        except Exception as e:
            frappe.log_error(str(e), "WhatsApp QR Generation")
            return {"url": url, "qr": None, "error": str(e)}
