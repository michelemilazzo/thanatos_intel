"""QR handoff per firma: desktop genera QR, telefono firma.

Flow universale:
1. Cliente apre /portal/ddd/sign?mandate=MND-... su desktop
2. Sceglie metodo (MMOS Sign/Documenso/OpenSign/LibreSign/...)
3. Backend chiama provider → riceve sign_url
4. Genera QR PNG dell'URL e lo restituisce
5. Cliente scansiona col telefono → completa firma sul mobile
6. Desktop polla lo stato fino a 'Signed'
"""
import io
import base64
import frappe
import qrcode


def _qr_png_base64(url: str, size: int = 10) -> str:
    qr = qrcode.QRCode(box_size=size, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0A0E1A", back_color="white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@frappe.whitelist(methods=["POST"])
def create_qr_signing(mandate: str, method: str) -> dict:
    """Lancia il metodo, prende il sign_url, genera QR.

    Per provider che hanno 'sign_url' nel ritorno (MMOS Sign, OpenSign,
    LibreSign), incorpora direttamente. Per Documenso/DocuSign che spediscono
    via email, costruisce un fallback link al sign URL del provider.
    """
    from thanatos_intel.thanatos_ddd.signature_methods import dispatch
    res = dispatch(mandate, method)
    if res.get("error"):
        return res

    sign_url = (res.get("sign_url")
                or res.get("envelope_url")
                or res.get("status_url"))
    if not sign_url:
        # Fallback URL al portale firma interno (per SES/PAdES che girano locale)
        sign_url = f"{frappe.utils.get_url()}/portal/ddd/sign?mandate={mandate}"

    res["qr_png_base64"] = _qr_png_base64(sign_url, size=10)
    res["sign_url"] = sign_url
    return res


@frappe.whitelist()
def status(mandate: str) -> dict:
    m = frappe.db.get_value("Agency Mandate", mandate,
        ["status", "signature_ref", "signed_on", "mandate_pdf"], as_dict=True)
    return m or {}
