import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.models import Invoice
from app.services import storage
from app.services.settings_service import get_settings


class SmtpNotConfigured(Exception):
    pass


def send_email(
    db: Session,
    to: str,
    subject: str,
    body: str,
    attachment_content: bytes,
    attachment_filename: str,
    attachment_mime_type: str | None,
) -> None:
    settings = get_settings(db)
    if not settings.smtp_configured:
        raise SmtpNotConfigured("SMTP ist nicht konfiguriert (Einstellungen)")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = to
    msg.set_content(body)

    maintype, _, subtype = (attachment_mime_type or "application/octet-stream").partition("/")
    msg.add_attachment(
        attachment_content,
        maintype=maintype or "application",
        subtype=subtype or "octet-stream",
        filename=attachment_filename,
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


def send_invoice_copy(db: Session, invoice: Invoice, recipient: str) -> None:
    content = storage.read_file(invoice.file_path)
    body = (
        f"Absender: {invoice.sender_name or '-'}\n"
        f"Rechnungsnummer: {invoice.invoice_number or '-'}\n"
        f"Rechnungsdatum: {invoice.invoice_date or '-'}\n"
        f"Betrag: {invoice.amount_gross or '-'} {invoice.currency}\n"
    )
    send_email(
        db,
        to=recipient,
        subject=f"Rechnung: {invoice.invoice_number or invoice.file_original_name}",
        body=body,
        attachment_content=content,
        attachment_filename=invoice.file_original_name or f"rechnung_{invoice.id}",
        attachment_mime_type=invoice.file_mime_type,
    )


def send_girocode(db: Session, invoice: Invoice, recipient: str, png_bytes: bytes) -> None:
    body = (
        f"Girocode zum Bezahlen der Rechnung von {invoice.payment_recipient_name or '-'}.\n"
        f"Betrag: {invoice.amount_gross or '-'} {invoice.currency}\n"
        f"IBAN: {invoice.payment_iban or '-'}\n"
        f"Verwendungszweck: {invoice.payment_reference or '-'}\n"
    )
    send_email(
        db,
        to=recipient,
        subject=f"Girocode: {invoice.invoice_number or invoice.file_original_name}",
        body=body,
        attachment_content=png_bytes,
        attachment_filename=f"girocode_rechnung_{invoice.id}.png",
        attachment_mime_type="image/png",
    )
