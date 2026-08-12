from sqlalchemy.orm import Session

from app.models import Invoice
from app.services import board_service, extraction, ocr, status, storage


def ingest_document(
    db: Session,
    content: bytes,
    original_filename: str,
    mime_type: str | None,
    source_type: str,
    source_detail: str | None = None,
    email_from: str | None = None,
) -> tuple[Invoice, bool]:
    """Speichert ein Dokument, extrahiert Felder per OCR und legt einen Invoice-Datensatz an.

    Gibt (invoice, is_new) zurueck. Bei einem bereits bekannten Dokument (gleicher
    Datei-Hash) wird der bestehende Datensatz zurueckgegeben und is_new=False gesetzt.

    Wirft storage.UnsupportedFileType, wenn der Dateityp nicht in der Allowlist steht.
    Die Pruefung sitzt bewusst hier und nicht in den Aufrufern: so ist sie fuer jeden
    Eingangsweg (Upload wie IMAP) automatisch aktiv, auch fuer spaeter ergaenzte.
    """
    if not storage.is_allowed_mime_type(mime_type):
        raise storage.UnsupportedFileType(
            f"Dateityp '{mime_type or 'unbekannt'}' wird nicht unterstützt "
            f"(erlaubt: PDF und Bilddateien)."
        )

    relative_path, file_hash = storage.save_file(content, original_filename)

    existing = db.query(Invoice).filter_by(file_hash_sha256=file_hash).first()
    if existing:
        return existing, False

    text = ocr.extract_text(content, mime_type)
    fields = extraction.extract_fields(text)

    invoice = Invoice(
        source_type=source_type,
        source_detail=source_detail,
        email_from=email_from,
        file_path=relative_path,
        file_original_name=original_filename,
        file_mime_type=mime_type,
        file_hash_sha256=file_hash,
        sender_name=fields.sender_name,
        invoice_number=fields.invoice_number,
        invoice_date=fields.invoice_date,
        amount_gross=fields.amount_gross,
        amount_net=fields.amount_net,
        vat_amount=fields.vat_amount,
        vat_rate=fields.vat_rate,
        raw_extracted_text=text or None,
        status="new",
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    status.change_status(db, invoice, "extracted")
    board_service.assign_to_default_column(db, invoice)
    return invoice, True
