from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSettings
from app.services.imap_client import (
    IMAP_FAILURE_ALERT_THRESHOLD,
    _register_failure_and_maybe_alert,
    _reset_failure_tracking,
    sync_new_invoices_standalone,
)


def test_standalone_sync_without_imap_configured_is_a_safe_noop():
    result = sync_new_invoices_standalone()
    assert result == {"new_invoices": 0, "duplicates": 0}


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _settings(db, **overrides):
    defaults = {
        "id": 1,
        "smtp_host": "smtp.example.invalid",
        "smtp_user": "me@example.invalid",
        "smtp_password": "secret",
        "reminder_email": "reminders@example.invalid",
    }
    defaults.update(overrides)
    settings = AppSettings(**defaults)
    db.add(settings)
    db.commit()
    return settings


def test_register_failure_increments_counter(db):
    _settings(db)
    with patch("app.services.imap_client.send_email"):
        _register_failure_and_maybe_alert(db)
    settings = db.get(AppSettings, 1)
    assert settings.imap_consecutive_failures == 1
    assert settings.imap_failure_notified_at is None


def test_register_failure_sends_alert_at_threshold(db):
    _settings(db)
    with patch("app.services.imap_client.send_email") as mock_send:
        for _ in range(IMAP_FAILURE_ALERT_THRESHOLD):
            _register_failure_and_maybe_alert(db)

    mock_send.assert_called_once()
    settings = db.get(AppSettings, 1)
    assert settings.imap_consecutive_failures == IMAP_FAILURE_ALERT_THRESHOLD
    assert settings.imap_failure_notified_at is not None


def test_register_failure_does_not_resend_alert_beyond_threshold(db):
    _settings(db)
    with patch("app.services.imap_client.send_email") as mock_send:
        for _ in range(IMAP_FAILURE_ALERT_THRESHOLD + 3):
            _register_failure_and_maybe_alert(db)

    mock_send.assert_called_once()


def test_register_failure_without_reminder_email_does_not_send(db):
    _settings(db, reminder_email=None)
    with patch("app.services.imap_client.send_email") as mock_send:
        for _ in range(IMAP_FAILURE_ALERT_THRESHOLD):
            _register_failure_and_maybe_alert(db)
    mock_send.assert_not_called()


def test_reset_failure_tracking_clears_counter_and_notified_flag(db):
    from datetime import datetime

    settings = _settings(db, imap_consecutive_failures=5, imap_failure_notified_at=datetime.utcnow())
    _reset_failure_tracking(db)
    db.refresh(settings)
    assert settings.imap_consecutive_failures == 0
    assert settings.imap_failure_notified_at is None
