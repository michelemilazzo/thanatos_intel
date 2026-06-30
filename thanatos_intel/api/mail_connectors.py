"""Thin wrapper — la logica è in mmos_brand.api.mail_connectors."""
from mmos_brand.api.mail_connectors import (
    list_connectors,
    add_connector,
    delete_connector,
    toggle_connector,
    test_connector,
    sync_now,
    microsoft_oauth_start,
    microsoft_oauth_finish,
    sync_all_connectors,
)

__all__ = [
    'list_connectors', 'add_connector', 'delete_connector',
    'toggle_connector', 'test_connector', 'sync_now',
    'microsoft_oauth_start', 'microsoft_oauth_finish', 'sync_all_connectors',
]
