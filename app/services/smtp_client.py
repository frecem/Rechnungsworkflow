import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.models import Invoice
from app.services import storage
from app.services.settings_service import get_settings


class SmtpNotConfigured(Exception):
    pass


def test_connection(host: str, port: int, user: str, password: str) -> tuple[bool, str]:
    """Prüft Verbindung + Login, ohne etwas zu versenden (fürs Setup gedacht)."""
    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(user, password)
        return True, "Verbindung und Login erfolgreich."
    except (smtplib.SMTPException, OSError) as exc:
        return False, f"Verbindung fehlgeschlagen: {exc}"


def send_test_mail(host: str, port: int, user: str, password: str, to: str) -> tuple[bool, str]:
    """Verschickt eine echte Testmail mit den (evtl. noch nicht gespeicherten) SMTP-Werten.

    Anders als test_connection() prueft das den kompletten Versandweg inkl. der
    Zustellung beim tatsaechlichen Empfaenger, nicht nur Verbindung/Login.
    """
    msg = EmailMessage()
    msg["Subject"] = "Testmail – Rechnungsworkflow"
    msg["From"] = user
    msg["To"] = to
    msg.set_content(
        "Das ist eine Testmail aus den SMTP-Einstellungen von Rechnungsworkflow.\n\n"
        "Wenn diese Mail ankommt, ist der Mailversand korrekt konfiguriert."
    )
    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True, f"Testmail an {to} gesendet."
    except (smtplib.SMTPException, OSError) as exc:
        return False, f"Versand fehlgeschlagen: {exc}"


def send_email(
    db: Session,
    to: str,
    subject: str,
    body: str,
    attachment_content: bytes | None = None,
    attachment_filename: str | None = None,
    attachment_mime_type: str | None = None,
) -> None:
    settings = get_settings(db)
    if not settings.smtp_configured:
        raise SmtpNotConfigured("SMTP ist nicht konfiguriert (Einstellungen)")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = to
    msg.set_content(body)

    if attachment_content is not None:
        maintype, _, subtype = (attachment_mime_type or "application/octet-stream").partition("/")
        msg.add_attachment(
            attachment_content,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=attachment_filename or "anhang",
        )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


def send_to_steuer(db: Session, invoice: Invoice, recipient: str) -> None:
    """Weiterleitung an die Steuer-App (z.B. Buhl Steuer-Scan).

    Bewusst ohne Text im Mailkörper: solche Apps werten den Anhang selbst per OCR
    aus, zusätzlicher Text im Betreff/Body bringt keinen Mehrwert und könnte die
    Erkennung eher stören.
    """
    content = storage.read_file(invoice.file_path)
    send_email(
        db,
        to=recipient,
        subject=invoice.invoice_number or invoice.file_original_name or f"Rechnung {invoice.id}",
        body="",
        attachment_content=content,
        attachment_filename=invoice.file_original_name or f"rechnung_{invoice.id}",
        attachment_mime_type=invoice.file_mime_type,
    )


def send_to_paperless(db: Session, invoice: Invoice, recipient: str) -> None:
    """Weiterleitung an Paperless-ngx' E-Mail-Eingang.

    Der Betreff enthält Absender + einen "aus dem Rechnungsworkflow"-Hinweis, damit
    das Dokument in Paperless-ngx auch ohne geöffneten Anhang klar zuzuordnen ist
    (z.B. in der Inbox-Übersicht oder falls dort Betreff-basierte Regeln laufen).
    """
    content = storage.read_file(invoice.file_path)
    sender = invoice.sender_name or "Unbekannter Absender"
    body = (
        f"Absender: {sender}\n"
        f"Rechnungsnummer: {invoice.invoice_number or '-'}\n"
        f"Rechnungsdatum: {invoice.invoice_date or '-'}\n"
        f"Betrag: {invoice.amount_gross or '-'} {invoice.currency}\n"
    )
    send_email(
        db,
        to=recipient,
        subject=f"{sender} – Rechnung aus dem Rechnungsworkflow",
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
