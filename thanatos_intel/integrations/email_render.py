"""Renderer email responsive Thanatos (mobile-first, Outlook-safe).

Avvolge il corpo di QUALUNQUE email cliente in un guscio fluido: contenitore
centrato max-width 600px ma width 100% su mobile, font >=15px, niente larghezze
fisse, bottoni bulletproof (table-based) per Outlook. Niente patch core: si usa
passando il risultato come `message` a frappe.sendmail.
"""
import frappe

LOGO = "https://thanatos.onekeyco.com/assets/thanatos_intel/images/thanatos-logo-white.svg"
LOGO_PNG = "https://thanatos.onekeyco.com/assets/thanatos_intel/images/thanatos-logo.png"
NAVY = "#0D1B3E"
GOLD = "#C8A96E"


def button(label, url):
    """Bottone bulletproof (table) responsive."""
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:18px 0"><tr><td align="center" bgcolor="%s" '
        'style="border-radius:6px"><a href="%s" target="_blank" '
        'style="display:inline-block;padding:14px 28px;font-family:Arial,Helvetica,sans-serif;'
        'font-size:15px;font-weight:bold;color:#0A0E1A;text-decoration:none;border-radius:6px">'
        '%s</a></td></tr></table>' % (GOLD, url, frappe.utils.escape_html(label))
    )


def render(body_html, title="", preheader="", cta=None):
    """Avvolge body_html nel guscio responsive. cta opzionale = (label, url)."""
    cta_html = button(cta[0], cta[1]) if cta else ""
    pre = ('<div style="display:none;max-height:0;overflow:hidden;opacity:0">%s</div>'
           % frappe.utils.escape_html(preheader)) if preheader else ""
    title_html = ('<h1 style="margin:0 0 14px;font-family:Georgia,serif;font-size:20px;'
                  'line-height:1.3;color:%s">%s</h1>' % (NAVY, frappe.utils.escape_html(title))) if title else ""
    return """\
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  @media only screen and (max-width:620px) {{
    .tn-container {{ width:100%% !important; }}
    .tn-pad {{ padding:22px 18px !important; }}
  }}
</style>
{pre}
<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0"
       style="background:#f4f5f7;margin:0;padding:0">
  <tr><td align="center" style="padding:18px 12px">
    <table role="presentation" class="tn-container" width="600" cellpadding="0" cellspacing="0" border="0"
           style="width:600px;max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;
                  border:1px solid #e3e6ea">
      <tr><td style="background:{navy};padding:18px 24px" align="left">
        <img src="{logo}" alt="Thanatos Intel" height="30" style="height:30px;display:block;border:0">
      </td></tr>
      <tr><td class="tn-pad" style="padding:28px 28px 8px;font-family:Arial,Helvetica,sans-serif;
              font-size:15px;line-height:1.6;color:#1a2230">
        {title}
        {body}
        {cta}
      </td></tr>
      <tr><td class="tn-pad" style="padding:18px 28px 26px;font-family:Arial,Helvetica,sans-serif;
              font-size:12px;line-height:1.5;color:#8a93a3;border-top:1px solid #eef0f3">
        Thanatos Intel · Investigazioni &amp; OSINT<br>
        <a href="https://thanatos.onekeyco.com" style="color:{gold};text-decoration:none">thanatos.onekeyco.com</a>
        · <a href="https://thanatos.onekeyco.com/portal" style="color:{gold};text-decoration:none">Area clienti</a>
      </td></tr>
    </table>
  </td></tr>
</table>""".format(pre=pre, navy=NAVY, gold=GOLD, logo=LOGO_PNG,
                   title=title_html, body=body_html or "", cta=cta_html)
