"""Renderer email responsive Thanatos (mobile-first, fluid-hybrid, Outlook-safe).

Pattern fluid-hybrid: su mobile il contenitore e' fluido (width:100% dentro un
div max-width:600), su Outlook resta a 600px via commenti condizionali MSO. Non
dipende dal supporto di <style>/@media (Gmail app li strippa): la responsivita'
viene dal layout fluido. Niente larghezze fisse, font >=16px, immagini scalabili,
bottoni bulletproof.
"""
import frappe

LOGO_PNG = "https://thanatos.agency/assets/thanatos_intel/images/thanatos-logo.png"
NAVY = "#0D1B3E"
GOLD = "#C8A96E"


def button(label, url):
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:20px 0"><tr><td align="center" bgcolor="%s" style="border-radius:6px">'
        '<a href="%s" target="_blank" style="display:inline-block;padding:14px 26px;'
        'font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:bold;color:#0A0E1A;'
        'text-decoration:none;border-radius:6px">%s</a></td></tr></table>'
        % (GOLD, url, frappe.utils.escape_html(label))
    )


def render(body_html, title="", preheader="", cta=None):
    cta_html = button(cta[0], cta[1]) if cta else ""
    pre = ('<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;opacity:0">%s</div>'
           % frappe.utils.escape_html(preheader)) if preheader else ""
    title_html = ('<h1 class="tn-h1" style="margin:0 0 16px;font-family:Georgia,serif;font-size:22px;'
                  'line-height:1.3;color:%s;font-weight:normal">%s</h1>'
                  % (NAVY, frappe.utils.escape_html(title))) if title else ""
    return """\
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<style>
  body{{margin:0;padding:0;width:100%!important;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}}
  img{{border:0;line-height:100%;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic;max-width:100%;height:auto}}
  table{{border-collapse:collapse}}
  @media only screen and (max-width:600px){{
    .tn-card{{width:100%!important;border-radius:0!important}}
    .tn-pad{{padding:22px 18px!important}}
    .tn-h1{{font-size:20px!important}}
  }}
</style>
{pre}
<div style="background:#f4f5f7;margin:0;padding:0;width:100%">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4f5f7">
  <tr><td align="center" style="padding:16px 10px">
    <!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
    <div class="tn-card" style="width:100%;max-width:600px;margin:0 auto;background:#ffffff;border-radius:8px;overflow:hidden;border:1px solid #e3e6ea">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr><td style="background:{navy};padding:18px 22px" align="left">
          <img src="{logo}" alt="Thanatos Intel" width="150" style="width:150px;max-width:60%;height:auto;display:block;border:0">
        </td></tr>
        <tr><td class="tn-pad" style="padding:30px 28px 10px;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.6;color:#1a2230">
          {title}
          {body}
          {cta}
        </td></tr>
        <tr><td class="tn-pad" style="padding:18px 28px 26px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.6;color:#8a93a3;border-top:1px solid #eef0f3">
          Thanatos Intel &middot; Investigazioni &amp; OSINT<br>
          <a href="https://thanatos.agency" style="color:{gold};text-decoration:none">thanatos.agency</a>
          &middot; <a href="https://thanatos.agency/portal" style="color:{gold};text-decoration:none">Area clienti</a>
        </td></tr>
      </table>
    </div>
    <!--[if mso]></td></tr></table><![endif]-->
  </td></tr>
</table>
</div>""".format(pre=pre, navy=NAVY, gold=GOLD, logo=LOGO_PNG,
                 title=title_html, body=body_html or "", cta=cta_html)
