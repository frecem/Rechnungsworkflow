"""Read-only IMAP-Abruf neuer Rechnungsanhänge.

Verbindet sich per IMAP4_SSL im readonly-Modus (keine E-Mails werden veraendert/geloescht),
sucht nach Nachrichten mit einer hoeheren UID als beim letzten Sync (getrackt in der
sync_state-Tabelle) und speist gefundene PDF-/Bild-Anhaenge in dieselbe
Ingest-Pipeline wie der manuelle Upload ein.
"""

import contextlib
import email
import imaplib
import logging
from datetime import datetime
from email.header import decode_header
from email.utils import parseaddr

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import SyncState
from app.services.ingest import ingest_document
from app.services.settings_service import get_settings
from app.services.smtp_client import send_email
from app.services.storage import ALLOWED_MIME_TYPES

logger = logging.getLogger(__name__)

# Frueher Filter beim Durchgehen der Mail-Anhaenge, damit irrelevante Teile
# (Signaturbilder, HTML-Body) gar nicht erst heruntergeladen und geOCRt werden.
# Die verbindliche Pruefung sitzt in ingest_document().
ALLOWED_CONTENT_TYPES = ALLOWED_MIME_TYPES

IMAP_FAILURE_ALERT_THRESHOLD = 3


class ImapNotConfigured(Exception):
    pass


def test_connection(host: str, port: int, user: str, password: str, mailbox: str) -> tuple[bool, str]:
    """Prüft Login + Postfachzugriff, ohne etwas zu importieren (fürs Setup gedacht)."""
    try:
        imap = imaplib.IMAP4_SSL(host, port, timeout=10)
        try:
            imap.login(user, password)
            result, data = imap.select(mailbox, readonly=True)
            if result != "OK":
                return False, f"Postfach '{mailbox}' konnte nicht geöffnet werden."
            count = int(data[0]) if data and data[0] else 0
            return True, f"Verbindung erfolgreich, {count} Nachricht(en) im Postfach '{mailbox}'."
        finally:
            with contextlib.suppress(Exception):
                imap.logout()
    except (imaplib.IMAP4.error, OSError) as exc:
        return False, f"Verbindung fehlgeschlagen: {exc}"


def _decode_maybe(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    return "".join(
        part.decode(encoding or "utf-8", errors="replace") if isinstance(part, bytes) else part
        for part, encoding in parts
    )


def _get_or_create_sync_state(db: Session, mailbox: str) -> SyncState:
    sync_state = db.query(SyncState).filter_by(mailbox=mailbox).first()
    if sync_state is None:
        sync_state = SyncState(mailbox=mailbox, last_uid=0)
        db.add(sync_state)
        db.commit()
        db.refresh(sync_state)
    return sync_state


def _extract_attachments(msg: email.message.Message) -> list[tuple[str, str, bytes]]:
    """Gibt Liste von (dateiname, content_type, inhalt) fuer relevante Anhaenge zurueck."""
    attachments = []
    for part in msg.walk():
        content_type = part.get_content_type()
        disposition = part.get("Content-Disposition", "")
        if content_type not in ALLOWED_CONTENT_TYPES:
            continue
        if "attachment" not in disposition and not part.get_filename():
            continue
        filename = _decode_maybe(part.get_filename()) or "anhang"
        payload = part.get_payload(decode=True)
        if payload:
            attachments.append((filename, content_type, payload))
    return attachments


def sync_new_invoices(db: Session) -> dict:
    settings = get_settings(db)
    if not settings.imap_configured:
        raise ImapNotConfigured("IMAP ist nicht konfiguriert (Einstellungen)")

    sync_state = _get_or_create_sync_state(db, settings.imap_mailbox)
    new_invoices = 0
    duplicates = 0
    highest_uid = sync_state.last_uid

    imap = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
    try:
        imap.login(settings.imap_user, settings.imap_app_password)
        imap.select(settings.imap_mailbox, readonly=True)

        search_range = f"{sync_state.last_uid + 1}:*"
        result, data = imap.uid("search", None, f"UID {search_range}")
        if result != "OK":
            return {"new_invoices": 0, "duplicates": 0, "error": "IMAP-Suche fehlgeschlagen"}

        uids = [int(u) for u in data[0].split() if int(u) > sync_state.last_uid]

        for uid in sorted(uids):
            result, msg_data = imap.uid("fetch", str(uid), "(RFC822)")
            if result != "OK" or not msg_data or msg_data[0] is None:
                continue
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            email_from = parseaddr(msg.get("From", ""))[1]
            message_id = msg.get("Message-ID", f"uid:{uid}")

            for filename, content_type, payload in _extract_attachments(msg):
                invoice, is_new = ingest_document(
                    db,
                    content=payload,
                    original_filename=filename,
                    mime_type=content_type,
                    source_type="email",
                    source_detail=message_id,
                    email_from=email_from,
                )
                if is_new:
                    new_invoices += 1
                else:
                    duplicates += 1

            highest_uid = max(highest_uid, uid)
    finally:
        with contextlib.suppress(Exception):
            imap.logout()

    if highest_uid != sync_state.last_uid:
        sync_state.last_uid = highest_uid
        db.commit()

    return {"new_invoices": new_invoices, "duplicates": duplicates}


def _reset_failure_tracking(db: Session) -> None:
    settings = get_settings(db)
    if settings.imap_consecutive_failures or settings.imap_failure_notified_at:
        settings.imap_consecutive_failures = 0
        settings.imap_failure_notified_at = None
        db.commit()


def _register_failure_and_maybe_alert(db: Session) -> None:
    """Zaehlt aufeinanderfolgende Fehlschlaege und verschickt ab einem Schwellwert

    genau einmal eine Warn-Mail an die Erinnerungs-Adresse (kein Spam bei jedem
    weiteren stuendlichen Versuch, solange der Fehler anhaelt).
    """
    settings = get_settings(db)
    settings.imap_consecutive_failures += 1
    db.commit()

    if (
        settings.imap_consecutive_failures >= IMAP_FAILURE_ALERT_THRESHOLD
        and settings.imap_failure_notified_at is None
        and settings.reminder_email
        and settings.smtp_configured
    ):
        try:
            send_email(
                db,
                to=settings.reminder_email,
                subject="Rechnungsworkflow: automatischer E-Mail-Abruf schlägt fehl",
                body=(
                    f"Der automatische IMAP-Sync ist seit {settings.imap_consecutive_failures} "
                    "Versuchen in Folge fehlgeschlagen. Bitte die IMAP-Zugangsdaten in den "
                    "Einstellungen prüfen (z.B. abgelaufenes App-Passwort)."
                ),
            )
            settings.imap_failure_notified_at = datetime.utcnow()
            db.commit()
        except Exception:
            logger.warning("IMAP-Fehler-Benachrichtigung konnte nicht versendet werden", exc_info=True)


def sync_new_invoices_standalone() -> dict:
    """Einstiegspunkt für den stündlichen Scheduler-Job: eigene DB-Session, still

    übersprungen wenn IMAP nicht konfiguriert ist, Verbindungsfehler werden geloggt
    statt den Scheduler abstürzen zu lassen. Nach mehreren Fehlschlägen in Folge wird
    einmalig eine Warn-Mail verschickt.
    """
    db = SessionLocal()
    try:
        result = sync_new_invoices(db)
        _reset_failure_tracking(db)
        return result
    except ImapNotConfigured:
        return {"new_invoices": 0, "duplicates": 0}
    except (imaplib.IMAP4.error, OSError):
        logger.warning("Automatischer IMAP-Sync fehlgeschlagen", exc_info=True)
        _register_failure_and_maybe_alert(db)
        return {"new_invoices": 0, "duplicates": 0, "error": "Verbindung fehlgeschlagen"}
    finally:
        db.close()
