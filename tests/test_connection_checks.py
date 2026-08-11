import imaplib
import smtplib
from unittest.mock import MagicMock, patch

from app.services import imap_client, smtp_client


def test_imap_test_connection_success():
    with patch("app.services.imap_client.imaplib.IMAP4_SSL") as mock_imap_cls:
        mock_imap = MagicMock()
        mock_imap.select.return_value = ("OK", [b"5"])
        mock_imap_cls.return_value = mock_imap

        ok, message = imap_client.test_connection("imap.example.invalid", 993, "me", "secret", "INBOX")

    assert ok is True
    assert "5" in message
    mock_imap.login.assert_called_once_with("me", "secret")
    mock_imap.logout.assert_called_once()


def test_imap_test_connection_select_failure():
    with patch("app.services.imap_client.imaplib.IMAP4_SSL") as mock_imap_cls:
        mock_imap = MagicMock()
        mock_imap.select.return_value = ("NO", [None])
        mock_imap_cls.return_value = mock_imap

        ok, message = imap_client.test_connection("imap.example.invalid", 993, "me", "secret", "Wrongbox")

    assert ok is False
    assert "Wrongbox" in message


def test_imap_test_connection_connection_error():
    with patch("app.services.imap_client.imaplib.IMAP4_SSL", side_effect=OSError("Name or service not known")):
        ok, message = imap_client.test_connection("bad.invalid", 993, "me", "secret", "INBOX")

    assert ok is False
    assert "fehlgeschlagen" in message


def test_imap_test_connection_auth_error():
    with patch("app.services.imap_client.imaplib.IMAP4_SSL") as mock_imap_cls:
        mock_imap = MagicMock()
        mock_imap.login.side_effect = imaplib.IMAP4.error("authentication failed")
        mock_imap_cls.return_value = mock_imap

        ok, message = imap_client.test_connection("imap.example.invalid", 993, "me", "wrong", "INBOX")

    assert ok is False
    assert "fehlgeschlagen" in message


def test_smtp_test_connection_success():
    with patch("app.services.smtp_client.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        ok, message = smtp_client.test_connection("smtp.example.invalid", 587, "me", "secret")

    assert ok is True
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("me", "secret")


def test_smtp_test_connection_auth_error():
    with patch("app.services.smtp_client.smtplib.SMTP") as mock_smtp_cls:
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        ok, message = smtp_client.test_connection("smtp.example.invalid", 587, "me", "wrong")

    assert ok is False
    assert "fehlgeschlagen" in message


def test_smtp_test_connection_connection_error():
    with patch("app.services.smtp_client.smtplib.SMTP", side_effect=OSError("Name or service not known")):
        ok, message = smtp_client.test_connection("bad.invalid", 587, "me", "secret")

    assert ok is False
    assert "fehlgeschlagen" in message
