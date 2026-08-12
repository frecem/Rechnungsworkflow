from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSettings, Invoice
from app.services.reminders import (
    due_invoices_for_reminder,
    run_reminder_check,
    run_unprocessed_check,
    unprocessed_invoices,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def make_invoice(db, *, hash_suffix, status="approved", due_date=None, paid_at=None, reminder_sent_at=None, **kwargs):
    invoice = Invoice(
        source_type="upload",
        file_path=f"2026/{hash_suffix}.pdf",
        file_hash_sha256=f"hash-{hash_suffix}",
        status=status,
        due_date=due_date,
        paid_at=paid_at,
        due_reminder_sent_at=reminder_sent_at,
        sender_name=kwargs.pop("sender_name", "Testfirma"),
        amount_gross=kwargs.pop("amount_gross", Decimal("100.00")),
        **kwargs,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


TODAY = date(2026, 8, 11)


def test_due_invoices_includes_upcoming_within_window(db):
    inv = make_invoice(db, hash_suffix="a", due_date=TODAY + timedelta(days=2))
    result = due_invoices_for_reminder(db, days_before=3, today=TODAY)
    assert result == [inv]


def test_due_invoices_excludes_far_future(db):
    make_invoice(db, hash_suffix="b", due_date=TODAY + timedelta(days=10))
    result = due_invoices_for_reminder(db, days_before=3, today=TODAY)
    assert result == []


def test_due_invoices_includes_overdue(db):
    inv = make_invoice(db, hash_suffix="c", due_date=TODAY - timedelta(days=5))
    result = due_invoices_for_reminder(db, days_before=3, today=TODAY)
    assert result == [inv]


def test_due_invoices_excludes_ineligible_status(db):
    make_invoice(db, hash_suffix="d", status="reviewed", due_date=TODAY)
    result = due_invoices_for_reminder(db, days_before=3, today=TODAY)
    assert result == []


def test_due_invoices_excludes_paid(db):
    make_invoice(db, hash_suffix="e", due_date=TODAY, paid_at=TODAY)
    result = due_invoices_for_reminder(db, days_before=3, today=TODAY)
    assert result == []


def test_due_invoices_excludes_already_reminded(db):
    make_invoice(db, hash_suffix="f", due_date=TODAY, reminder_sent_at=TODAY)
    result = due_invoices_for_reminder(db, days_before=3, today=TODAY)
    assert result == []


def test_due_invoices_excludes_no_due_date(db):
    make_invoice(db, hash_suffix="g", due_date=None)
    result = due_invoices_for_reminder(db, days_before=3, today=TODAY)
    assert result == []


def _settings(db, **overrides):
    defaults = {
        "id": 1,
        "smtp_host": "smtp.example.invalid",
        "smtp_user": "me@example.invalid",
        "smtp_password": "secret",
        "reminder_email": "reminders@example.invalid",
        "reminder_days_before": 3,
        "last_backup_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    settings = AppSettings(**defaults)
    db.add(settings)
    db.commit()
    return settings


def test_run_reminder_check_without_reminder_email_returns_zero(db):
    _settings(db, reminder_email=None)
    make_invoice(db, hash_suffix="h", due_date=date.today())
    with patch("app.services.reminders.send_email") as mock_send:
        count = run_reminder_check(db)
    assert count == 0
    mock_send.assert_not_called()


def test_run_reminder_check_sends_digest_and_marks_invoices(db):
    _settings(db)
    inv1 = make_invoice(db, hash_suffix="i", due_date=date.today())
    inv2 = make_invoice(db, hash_suffix="j", due_date=date.today() - timedelta(days=1))

    with patch("app.services.reminders.send_email") as mock_send:
        count = run_reminder_check(db)

    assert count == 2
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "reminders@example.invalid"
    assert "Testfirma" in call_kwargs["body"]
    assert "ÜBERFÄLLIG" in call_kwargs["body"]

    db.refresh(inv1)
    db.refresh(inv2)
    assert inv1.due_reminder_sent_at is not None
    assert inv2.due_reminder_sent_at is not None


def test_run_reminder_check_no_due_invoices_returns_zero(db):
    _settings(db)
    with patch("app.services.reminders.send_email") as mock_send:
        count = run_reminder_check(db)
    assert count == 0
    mock_send.assert_not_called()


def test_run_reminder_check_send_failure_does_not_mark_reminded(db):
    from app.services.smtp_client import SmtpNotConfigured

    _settings(db)
    inv = make_invoice(db, hash_suffix="k", due_date=date.today())

    with patch("app.services.reminders.send_email", side_effect=SmtpNotConfigured("nope")):
        count = run_reminder_check(db)

    assert count == 0
    db.refresh(inv)
    assert inv.due_reminder_sent_at is None


def test_run_reminder_check_connection_error_does_not_raise(db):
    """Regression: ein unerreichbarer SMTP-Host darf den Aufrufer nicht mit einer

    unbehandelten Exception abstuerzen lassen (fruehere Version fing nur
    SmtpNotConfigured ab, nicht smtplib/OSError-Fehler wie socket.gaierror).
    """
    _settings(db)
    inv = make_invoice(db, hash_suffix="n", due_date=date.today())

    with patch("app.services.reminders.send_email", side_effect=OSError("Name or service not known")):
        count = run_reminder_check(db)

    assert count == 0
    db.refresh(inv)
    assert inv.due_reminder_sent_at is None


def test_run_reminder_check_includes_overdue_recurring_even_without_due_invoices(db):
    _settings(db)
    make_invoice(
        db,
        hash_suffix="l",
        sender_name="Vermieter GmbH",
        invoice_date=date.today() - timedelta(days=60),
        is_recurring=True,
        recurrence_interval_days=30,
    )

    with patch("app.services.reminders.send_email") as mock_send:
        count = run_reminder_check(db)

    # keine faelligen Rechnungen (kein due_date gesetzt) -> Rueckgabewert bleibt 0,
    # trotzdem wird eine Mail wegen der ueberfaelligen wiederkehrenden Zahlung verschickt
    assert count == 0
    mock_send.assert_called_once()
    body = mock_send.call_args.kwargs["body"]
    assert "Vermieter GmbH" in body
    assert "wiederkehrend" in body.lower() or "erwarteter" in body.lower()


def test_run_reminder_check_includes_backup_overdue_even_without_due_invoices(db):
    _settings(db, last_backup_at=None)

    with patch("app.services.reminders.send_email") as mock_send:
        count = run_reminder_check(db)

    assert count == 0
    mock_send.assert_called_once()
    assert "Backup" in mock_send.call_args.kwargs["body"]


def test_run_reminder_check_no_alert_for_recurring_within_grace_period(db):
    _settings(db)
    make_invoice(
        db,
        hash_suffix="m",
        sender_name="Netflix",
        invoice_date=date.today() - timedelta(days=10),
        is_recurring=True,
        recurrence_interval_days=30,
    )

    with patch("app.services.reminders.send_email") as mock_send:
        count = run_reminder_check(db)

    assert count == 0
    mock_send.assert_not_called()


def test_unprocessed_invoices_includes_only_pending_statuses(db):
    new_inv = make_invoice(db, hash_suffix="o", status="new")
    extracted_inv = make_invoice(db, hash_suffix="p", status="extracted")
    reviewed_inv = make_invoice(db, hash_suffix="q", status="reviewed")
    make_invoice(db, hash_suffix="r", status="approved")
    make_invoice(db, hash_suffix="s", status="forwarded")
    make_invoice(db, hash_suffix="t", status="rejected")

    result = unprocessed_invoices(db)

    assert {inv.id for inv in result} == {new_inv.id, extracted_inv.id, reviewed_inv.id}


def test_run_unprocessed_check_sends_digest(db):
    _settings(db)
    make_invoice(db, hash_suffix="u", status="new", sender_name="Vermieter GmbH")
    make_invoice(db, hash_suffix="v", status="extracted")

    with patch("app.services.reminders.send_email") as mock_send:
        count = run_unprocessed_check(db)

    assert count == 2
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "reminders@example.invalid"
    assert "Vermieter GmbH" in call_kwargs["body"]
    assert "2" in call_kwargs["subject"]


def test_run_unprocessed_check_no_pending_invoices_returns_zero(db):
    _settings(db)
    make_invoice(db, hash_suffix="w", status="approved")

    with patch("app.services.reminders.send_email") as mock_send:
        count = run_unprocessed_check(db)

    assert count == 0
    mock_send.assert_not_called()


def test_run_unprocessed_check_without_reminder_email_returns_zero(db):
    _settings(db, reminder_email=None)
    make_invoice(db, hash_suffix="x", status="new")

    with patch("app.services.reminders.send_email") as mock_send:
        count = run_unprocessed_check(db)

    assert count == 0
    mock_send.assert_not_called()


def test_run_unprocessed_check_connection_error_does_not_raise(db):
    _settings(db)
    make_invoice(db, hash_suffix="y", status="new")

    with patch("app.services.reminders.send_email", side_effect=OSError("Name or service not known")):
        count = run_unprocessed_check(db)

    assert count == 0
