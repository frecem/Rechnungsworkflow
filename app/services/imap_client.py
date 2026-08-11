"""Read-only IMAP-Abruf neuer Rechnungsanhänge.

Verbindet sich per IMAP4_SSL im readonly-Modus (keine E-Mails werden veraendert/geloescht),
sucht nach Nachrichten mit einer hoeheren UID als beim letzten Sync (getrackt in der
sync_state-Tabelle) und speist gefundene PDF-/Bild-Anhaenge in dieselbe
Ingest-Pipeline wie der manuelle Upload ein.
"""

import email
import imaplib
from email.header import decode_header
from email.utils import parseaddr

from sqlalchemy.orm import Session

from app.config import settings
from app.models import SyncState
from app.services.ingest import ingest_document

ALLOWED_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}


class ImapNotConfigured(Exception):
    pass


def _decode_maybe(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    return "".join(
        part.decode(encoding or "utf-8", errors="replace") if isinstance(part, bytes) else part
        for part, encoding in parts
    )


def _get_or_create_sync_state(db: Session) -> SyncState:
    sync_state = db.query(SyncState).filter_by(mailbox=settings.imap_mailbox).first()
    if sync_state is None:
        sync_state = SyncState(mailbox=settings.imap_mailbox, last_uid=0)
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
    if not settings.imap_configured:
        raise ImapNotConfigured("IMAP ist nicht konfiguriert (.env)")

    sync_state = _get_or_create_sync_state(db)
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
        try:
            imap.logout()
        except Exception:
            pass

    if highest_uid != sync_state.last_uid:
        sync_state.last_uid = highest_uid
        db.commit()

    return {"new_invoices": new_invoices, "duplicates": duplicates}
