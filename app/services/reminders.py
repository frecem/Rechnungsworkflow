"""Fälligkeits-Erinnerung: prüft freigegebene, unbezahlte Rechnungen und schickt bei
Bedarf eine Sammel-E-Mail (ein Digest statt einer Mail pro Rechnung).
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Invoice
from app.services.settings_service import get_settings
from app.services.smtp_client import SmtpNotConfigured, send_email

REMINDER_ELIGIBLE_STATUSES = ("approved", "forwarded")


def due_invoices_for_reminder(db: Session, days_before: int, today: date | None = None) -> list[Invoice]:
    """Rechnungen, die bald fällig oder bereits überfällig sind und noch keine Erinnerung bekamen.

    Eine einzige Bedingung (`due_date <= today + days_before`) deckt beide Fälle ab,
    da ein überfälliges Datum immer kleiner/gleich diesem Grenzwert ist.
    """
    today = today or date.today()
    cutoff = today + timedelta(days=days_before)
    return (
        db.query(Invoice)
        .filter(Invoice.status.in_(REMINDER_ELIGIBLE_STATUSES))
        .filter(Invoice.paid_at.is_(None))
        .filter(Invoice.due_reminder_sent_at.is_(None))
        .filter(Invoice.due_date.isnot(None))
        .filter(Invoice.due_date <= cutoff)
        .order_by(Invoice.due_date.asc())
        .all()
    )


def _format_digest(invoices: list[Invoice], today: date) -> str:
    lines = [f"Fälligkeits-Erinnerung ({today.isoformat()}):", ""]
    for inv in invoices:
        overdue = " (ÜBERFÄLLIG)" if inv.due_date and inv.due_date < today else ""
        lines.append(
            f"- #{inv.id} {inv.sender_name or 'Unbekannt'} – "
            f"{inv.amount_gross or '-'} {inv.currency} – fällig am {inv.due_date}{overdue}"
        )
    lines.append("")
    lines.append("Zum Bearbeiten: Rechnungsübersicht in Rechnungsworkflow öffnen.")
    return "\n".join(lines)


def run_reminder_check(db: Session) -> int:
    """Führt den Fälligkeits-Check aus, versendet ggf. eine Sammel-Mail.

    Gibt die Anzahl der Rechnungen zurück, für die eine Erinnerung verschickt wurde
    (0, wenn nichts fällig ist oder Erinnerungen nicht konfiguriert sind).
    """
    settings = get_settings(db)
    if not settings.reminder_email or not settings.smtp_configured:
        return 0

    invoices = due_invoices_for_reminder(db, settings.reminder_days_before)
    if not invoices:
        return 0

    body = _format_digest(invoices, date.today())
    try:
        send_email(
            db,
            to=settings.reminder_email,
            subject=f"Fälligkeits-Erinnerung: {len(invoices)} Rechnung(en)",
            body=body,
        )
    except SmtpNotConfigured:
        return 0

    now = datetime.utcnow()
    for inv in invoices:
        inv.due_reminder_sent_at = now
    db.commit()
    return len(invoices)


def run_reminder_check_standalone() -> int:
    """Einstiegspunkt für den Scheduler-Job: öffnet/schließt eine eigene DB-Session."""
    db = SessionLocal()
    try:
        return run_reminder_check(db)
    finally:
        db.close()
