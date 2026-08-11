from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSettings
from app.services import password_reset
from app.services.auth import verify_password


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
    defaults = dict(
        id=1,
        admin_password_hash="old-hash",
        smtp_host="smtp.example.invalid",
        smtp_user="me@example.invalid",
        smtp_password="secret",
        reminder_email="me@example.invalid",
    )
    defaults.update(overrides)
    settings = AppSettings(**defaults)
    db.add(settings)
    db.commit()
    return settings


def test_request_reset_without_reminder_email_fails(db):
    _settings(db, reminder_email=None)
    with patch("app.services.password_reset.send_email") as mock_send:
        ok, message = password_reset.request_reset(db, "http://localhost:8000")
    assert ok is False
    assert "CLI" in message
    mock_send.assert_not_called()


def test_request_reset_without_smtp_fails(db):
    _settings(db, smtp_host=None)
    with patch("app.services.password_reset.send_email") as mock_send:
        ok, message = password_reset.request_reset(db, "http://localhost:8000")
    assert ok is False
    mock_send.assert_not_called()


def test_request_reset_sends_link_and_sets_token(db):
    settings = _settings(db)
    with patch("app.services.password_reset.send_email") as mock_send:
        ok, message = password_reset.request_reset(db, "http://localhost:8000")

    assert ok is True
    mock_send.assert_called_once()
    body = mock_send.call_args.kwargs["body"]
    db.refresh(settings)
    assert settings.password_reset_token in body
    assert "/reset-password?token=" in body


def test_request_reset_reuses_existing_valid_token(db):
    settings = _settings(db)
    with patch("app.services.password_reset.send_email"):
        password_reset.request_reset(db, "http://localhost:8000")
    db.refresh(settings)
    first_token = settings.password_reset_token

    with patch("app.services.password_reset.send_email"):
        password_reset.request_reset(db, "http://localhost:8000")
    db.refresh(settings)
    assert settings.password_reset_token == first_token


def test_request_reset_generates_new_token_after_expiry(db):
    settings = _settings(db)
    with patch("app.services.password_reset.send_email"):
        password_reset.request_reset(db, "http://localhost:8000")
    db.refresh(settings)
    first_token = settings.password_reset_token
    settings.password_reset_token_expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    with patch("app.services.password_reset.send_email"):
        password_reset.request_reset(db, "http://localhost:8000")
    db.refresh(settings)
    assert settings.password_reset_token != first_token


def test_request_reset_send_failure_reports_error(db):
    import smtplib

    _settings(db)
    with patch("app.services.password_reset.send_email", side_effect=smtplib.SMTPException("boom")):
        ok, message = password_reset.request_reset(db, "http://localhost:8000")
    assert ok is False
    assert "CLI" in message


def test_validate_token_accepts_valid_token(db):
    settings = _settings(
        db,
        password_reset_token="abc123",
        password_reset_token_expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    assert password_reset.validate_token(db, "abc123") is True


def test_validate_token_rejects_wrong_token(db):
    _settings(
        db,
        password_reset_token="abc123",
        password_reset_token_expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    assert password_reset.validate_token(db, "wrong") is False


def test_validate_token_rejects_expired_token(db):
    _settings(
        db,
        password_reset_token="abc123",
        password_reset_token_expires_at=datetime.utcnow() - timedelta(minutes=1),
    )
    assert password_reset.validate_token(db, "abc123") is False


def test_validate_token_rejects_missing_token(db):
    _settings(db, password_reset_token=None)
    assert password_reset.validate_token(db, "") is False


def test_complete_reset_sets_new_password_and_clears_token(db):
    settings = _settings(
        db,
        password_reset_token="abc123",
        password_reset_token_expires_at=datetime.utcnow() + timedelta(minutes=10),
    )
    result = password_reset.complete_reset(db, "abc123", "newpassword123")

    assert result is True
    db.refresh(settings)
    assert verify_password("newpassword123", settings.admin_password_hash)
    assert settings.password_reset_token is None
    assert settings.password_reset_token_expires_at is None


def test_complete_reset_rejects_invalid_token(db):
    settings = _settings(db, password_reset_token=None)
    result = password_reset.complete_reset(db, "nope", "newpassword123")

    assert result is False
    db.refresh(settings)
    assert settings.admin_password_hash == "old-hash"
