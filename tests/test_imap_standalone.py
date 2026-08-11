from app.services.imap_client import sync_new_invoices_standalone


def test_standalone_sync_without_imap_configured_is_a_safe_noop():
    result = sync_new_invoices_standalone()
    assert result == {"new_invoices": 0, "duplicates": 0}
