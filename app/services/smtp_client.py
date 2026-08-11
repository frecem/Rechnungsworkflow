import smtplib
from email.message import EmailMessage

from app.config import settings
from app.models import Invoice
from app.services import storage


class SmtpNotConfigured(Exception):
    pass


def send_invoice(invoice: Invoice, recipient: str) -> None:
    if not settings.smtp_configured:
        raise SmtpNotConfigured("SMTP ist nicht konfiguriert (.env)")

    content = storage.read_file(invoice.file_path)

    msg = EmailMessage()
    msg["Subject"] = f"Weitergeleitete Rechnung: {invoice.invoice_number or invoice.file_original_name}"
    msg["From"] = settings.smtp_user
    msg["To"] = recipient
    body = (
        f"Absender: {invoice.sender_name or '-'}\n"
        f"Rechnungsnummer: {invoice.invoice_number or '-'}\n"
        f"Rechnungsdatum: {invoice.invoice_date or '-'}\n"
        f"Betrag: {invoice.amount_gross or '-'} {invoice.currency}\n"
    )
    msg.set_content(body)

    maintype, _, subtype = (invoice.file_mime_type or "application/octet-stream").partition("/")
    msg.add_attachment(
        content,
        maintype=maintype or "application",
        subtype=subtype or "octet-stream",
        filename=invoice.file_original_name or f"rechnung_{invoice.id}",
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
