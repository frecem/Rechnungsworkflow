"""Fälligkeits-Erinnerung: prüft freigegebene, unbezahlte Rechnungen und schickt bei
Bedarf eine Sammel-E-Mail (ein Digest statt einer Mail pro Rechnung).
"""

import logging
import smtplib
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Invoice
from app.services.backup import BACKUP_REMINDER_DAYS, is_backup_overdue
from app.services.settings_service import get_settings
from app.services.smtp_client import SmtpNotConfigured, send_email
from app.services.stats import RecurringGroup, recurring_overview

REMINDER_ELIGIBLE_STATUSES = ("approved", "forwarded")

# Stati, die noch eine Aktion auf dem Board brauchen (Prüfen/Freigeben/Ablehnen) -
# alles davor/danach (approved/forwarded/rejected) ist bereits abgeschlossen.
UNPROCESSED_STATUSES = ("new", "extracted", "reviewed")

logger = logging.getLogger(__name__)


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


def overdue_recurring_groups(db: Session, today: date | None = None) -> list[RecurringGroup]:
    """Wiederkehrende Zahlungsserien (z.B. Miete, Abo), deren nächster erwarteter Beleg

    überfällig ist (Intervall der letzten Rechnung + Kulanzfrist verstrichen, aber keine
    neue Rechnung eingetroffen).
    """
    invoices = db.query(Invoice).filter(Invoice.invoice_date.isnot(None)).all()
    return [g for g in recurring_overview(invoices, today=today) if g.is_overdue]


def _format_digest(
    invoices: list[Invoice],
    overdue_recurring: list[RecurringGroup],
    backup_overdue: bool,
    today: date,
) -> str:
    lines = [f"Erinnerung ({today.isoformat()}):", ""]

    if invoices:
        lines.append("Fällige/überfällige Rechnungen:")
        for inv in invoices:
            overdue = " (ÜBERFÄLLIG)" if inv.due_date and inv.due_date < today else ""
            lines.append(
                f"- #{inv.id} {inv.sender_name or 'Unbekannt'} – "
                f"{inv.amount_gross or '-'} {inv.currency} – fällig am {inv.due_date}{overdue}"
            )
        lines.append("")

    if overdue_recurring:
        lines.append("Erwarteter wiederkehrender Beleg fehlt noch:")
        for group in overdue_recurring:
            lines.append(
                f"- {group.label}: letzte Rechnung am {group.last_date}, "
                f"erwartet ab {group.expected_next} (Intervall {group.interval_days} Tage)"
            )
        lines.append("")

    if backup_overdue:
        lines.append(
            f"Backup überfällig: seit mind. {BACKUP_REMINDER_DAYS} Tagen kein Backup "
            "mehr heruntergeladen (Einstellungen > Backup)."
        )
        lines.append("")

    lines.append("Zum Bearbeiten: Rechnungsübersicht in Rechnungsworkflow öffnen.")
    return "\n".join(lines)


def run_reminder_check(db: Session) -> int:
    """Führt den Fälligkeits- und Wiederkehrend-Check aus, versendet ggf. eine Sammel-Mail.

    Gibt die Anzahl der fälligen Rechnungen zurück, für die eine Erinnerung verschickt
    wurde (0, wenn nichts fällig/überfällig ist oder Erinnerungen nicht konfiguriert
    sind) - überfällige wiederkehrende Serien fließen zusätzlich in dieselbe Mail ein,
    zählen aber nicht in den Rückgabewert hinein.
    """
    settings = get_settings(db)
    if not settings.reminder_email or not settings.smtp_configured:
        return 0

    invoices = due_invoices_for_reminder(db, settings.reminder_days_before)
    overdue_recurring = overdue_recurring_groups(db)
    backup_overdue = is_backup_overdue(settings)
    if not invoices and not overdue_recurring and not backup_overdue:
        return 0

    body = _format_digest(invoices, overdue_recurring, backup_overdue, date.today())
    subject_parts = []
    if invoices:
        subject_parts.append(f"{len(invoices)} Rechnung(en)")
    if overdue_recurring:
        subject_parts.append(f"{len(overdue_recurring)} wiederkehrende Zahlung(en)")
    if backup_overdue:
        subject_parts.append("Backup überfällig")

    try:
        send_email(
            db,
            to=settings.reminder_email,
            subject=f"Erinnerung: {', '.join(subject_parts)}",
            body=body,
        )
    except SmtpNotConfigured:
        return 0
    except (smtplib.SMTPException, OSError):
        logger.warning("Versand der Fälligkeits-Erinnerung fehlgeschlagen", exc_info=True)
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


def unprocessed_invoices(db: Session) -> list[Invoice]:
    """Rechnungen, die noch eine Board-Aktion brauchen (noch nicht freigegeben/abgelehnt)."""
    return (
        db.query(Invoice)
        .filter(Invoice.status.in_(UNPROCESSED_STATUSES))
        .order_by(Invoice.created_at.asc())
        .all()
    )


def _format_unprocessed_digest(invoices: list[Invoice], today: date) -> str:
    lines = [f"Unbearbeitete Rechnungen ({today.isoformat()}):", ""]
    for inv in invoices:
        lines.append(
            f"- #{inv.id} {inv.sender_name or 'Unbekannt'} – "
            f"{inv.amount_gross or '-'} {inv.currency} – Status: {inv.status}"
        )
    lines.append("")
    lines.append("Zum Bearbeiten: Board in Rechnungsworkflow öffnen.")
    return "\n".join(lines)


def run_unprocessed_check(db: Session) -> int:
    """Erinnert an Rechnungen, die noch nicht geprüft/freigegeben wurden.

    Läuft werktags morgens und am Wochenende etwas später (siehe app.main), zusätzlich
    zum stündlichen IMAP-Sync - neue Rechnungen können also jederzeit einzeln bearbeitet
    werden, ohne auf diesen Digest zu warten. Es gibt bewusst kein "schon erinnert"-Flag
    wie bei der Fälligkeits-Erinnerung: solange eine Rechnung unbearbeitet bleibt, soll
    sie jeden Tag erneut auftauchen; sobald sie freigegeben/abgelehnt wird, fällt sie
    automatisch aus der Status-Filterung heraus und erscheint am nächsten Tag nicht mehr.
    """
    settings = get_settings(db)
    if not settings.reminder_email or not settings.smtp_configured:
        return 0

    invoices = unprocessed_invoices(db)
    if not invoices:
        return 0

    try:
        send_email(
            db,
            to=settings.reminder_email,
            subject=f"{len(invoices)} unbearbeitete Rechnung(en)",
            body=_format_unprocessed_digest(invoices, date.today()),
        )
    except SmtpNotConfigured:
        return 0
    except (smtplib.SMTPException, OSError):
        logger.warning("Versand des Unbearbeitet-Digests fehlgeschlagen", exc_info=True)
        return 0

    return len(invoices)


def run_unprocessed_check_standalone() -> int:
    """Einstiegspunkt für den Scheduler-Job: öffnet/schließt eine eigene DB-Session."""
    db = SessionLocal()
    try:
        return run_unprocessed_check(db)
    finally:
        db.close()
