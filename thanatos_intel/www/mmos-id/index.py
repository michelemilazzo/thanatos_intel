"""Pagina pubblica MMOS ID — /mmos-id. Presentazione del servizio identità con passkey."""
no_cache = 1


def get_context(context):
    context.body_class = "ppu-page"
    return context
