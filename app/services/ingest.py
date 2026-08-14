from sqlalchemy.orm import Session

from app.models import Invoice
from app.services import board_service, extraction, ocr, qr_scan, status, storage


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
    # Viele Rechnungen (v.a. Versorger) drucken bereits einen Girocode/EPC-QR-Code
    # ab - wird einer gefunden, sind seine Zahlungsdaten zuverlaessiger als das
    # Erraten per Texterkennung und werden direkt vorbefuellt (siehe girocode_form
    # in app/routers/invoices.py, das invoice.payment_* vor der Regex-Suche prueft).
    # Der Girocode-Empfaengername und die Zahlungsreferenz sind ausserdem oft mit
    # Absender/Rechnungsnummer identisch, also auch dort als Fallback nutzen, wenn
    # die Texterkennung nichts gefunden hat.
    epc_payment = qr_scan.find_epc_payment_data(content, mime_type)

    invoice = Invoice(
        source_type=source_type,
        source_detail=source_detail,
        email_from=email_from,
        file_path=relative_path,
        file_original_name=original_filename,
        file_mime_type=mime_type,
        file_hash_sha256=file_hash,
        sender_name=fields.sender_name or (epc_payment["recipient_name"] if epc_payment else None),
        invoice_number=fields.invoice_number or (epc_payment["reference"] if epc_payment else None),
        invoice_date=fields.invoice_date,
        amount_gross=fields.amount_gross or (epc_payment["amount"] if epc_payment else None),
        amount_net=fields.amount_net,
        vat_amount=fields.vat_amount,
        vat_rate=fields.vat_rate,
        raw_extracted_text=text or None,
        payment_recipient_name=epc_payment["recipient_name"] if epc_payment else None,
        payment_iban=epc_payment["iban"] if epc_payment else None,
        payment_bic=epc_payment["bic"] if epc_payment else None,
        payment_reference=epc_payment["reference"] if epc_payment else None,
        status="new",
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    status.change_status(db, invoice, "extracted")
    board_service.assign_to_default_column(db, invoice)
    return invoice, True
