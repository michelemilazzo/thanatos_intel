"""
Patch mail.auth.ALLOWED_PATHS to include thanatos_intel guest endpoints.
Registered as auth_hooks in thanatos_intel — runs before mail.auth.validate.
"""


def allow_thanatos_guest_paths() -> None:
    try:
        import mail.auth as _mail_auth
    except ImportError:
        return

    _extra = [
        "/api/method/thanatos_intel.thanatos_ddd.docuseal.webhook",
        "/api/method/thanatos_intel.thanatos_ddd.docuseal.serve_mandate_pdf",
        "/api/method/thanatos_intel.thanatos_ddd.signature_methods.docuseal_webhook",
        "/api/method/thanatos_intel.thanatos_ddd.signature_methods.fetch_mandate_pdf",
        "/api/method/mmos_brand.password_sync.receive_password_sync",
        # mmos_sign guest e-signature flow (WAVE 2, additivo accanto a DocuSeal)
        "/sign",
        "/api/method/mmos_sign.api.get_request",
        "/api/method/mmos_sign.api.submit_signature",
    ]
    for path in _extra:
        if path not in _mail_auth.ALLOWED_PATHS:
            _mail_auth.ALLOWED_PATHS.append(path)
