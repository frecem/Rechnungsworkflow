import smtplib
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSettings, Invoice
from app.services import smtp_client


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def make_invoice(**overrides):
    defaults = dict(
        source_type="upload",
        file_path="2026/test.pdf",
        file_hash_sha256="hash-1",
        sender_name="Musterfirma GmbH",
        invoice_number="RE-2026-001",
        amount_gross=100,
        currency="EUR",
        file_original_name="rechnung.pdf",
        file_mime_type="application/pdf",
    )
    defaults.update(overrides)
    return Invoice(**defaults)


def test_send_test_mail_success():
    with patch("app.services.smtp_client.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        ok, message = smtp_client.send_test_mail("smtp.example.invalid", 587, "me", "secret", "you@example.invalid")

    assert ok is True
    assert "you@example.invalid" in message
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("me", "secret")
    mock_server.send_message.assert_called_once()
    sent_msg = mock_server.send_message.call_args.args[0]
    assert sent_msg["To"] == "you@example.invalid"
    assert "Testmail" in sent_msg["Subject"]


def test_send_test_mail_connection_error():
    with patch("app.services.smtp_client.smtplib.SMTP", side_effect=OSError("Name or service not known")):
        ok, message = smtp_client.send_test_mail("bad.invalid", 587, "me", "secret", "you@example.invalid")

    assert ok is False
    assert "fehlgeschlagen" in message


def test_send_to_steuer_has_empty_body_and_no_workflow_marker(db, monkeypatch):
    db.add(AppSettings(id=1, smtp_host="smtp.example.invalid", smtp_user="me", smtp_password="secret"))
    db.commit()
    monkeypatch.setattr(smtp_client.storage, "read_file", lambda path: b"%PDF-1.4 fake")

    invoice = make_invoice()
    with patch("app.services.smtp_client.send_email") as mock_send:
        smtp_client.send_to_steuer(db, invoice, "steuer@example.invalid")

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["to"] == "steuer@example.invalid"
    assert kwargs["body"] == ""
    assert "Rechnungsworkflow" not in kwargs["subject"]


def test_send_to_paperless_subject_has_sender_and_workflow_marker(db, monkeypatch):
    db.add(AppSettings(id=1, smtp_host="smtp.example.invalid", smtp_user="me", smtp_password="secret"))
    db.commit()
    monkeypatch.setattr(smtp_client.storage, "read_file", lambda path: b"%PDF-1.4 fake")

    invoice = make_invoice(sender_name="Musterfirma GmbH")
    with patch("app.services.smtp_client.send_email") as mock_send:
        smtp_client.send_to_paperless(db, invoice, "paperless@example.invalid")

    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert kwargs["to"] == "paperless@example.invalid"
    assert "Musterfirma GmbH" in kwargs["subject"]
    assert "Rechnungsworkflow" in kwargs["subject"]
    assert "Musterfirma GmbH" in kwargs["body"]
