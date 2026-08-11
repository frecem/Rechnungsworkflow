"""Passwort-Reset per E-Mail-Link, falls das Login-Passwort vergessen wurde.

Der Token wird in AppSettings (Singleton) gespeichert, nicht in einer eigenen
Tabelle - es gibt ohnehin nur einen Account. Eine erneute Anfrage während ein
gültiger Token existiert, verschickt denselben Link erneut statt einen neuen
zu erzeugen (natürliches Rate-Limiting gegen Mail-Spam).
"""

import logging
import secrets
import smtplib
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.services.auth import hash_password
from app.services.settings_service import get_settings
from app.services.smtp_client import SmtpNotConfigured, send_email

RESET_TOKEN_TTL_MINUTES = 30

logger = logging.getLogger(__name__)


def request_reset(db: Session, reset_url_base: str) -> tuple[bool, str]:
    """Erzeugt (oder verlängert nicht) einen Reset-Token und verschickt den Link.

    Ziel-Adresse ist reminder_email (die bereits als "eigene E-Mail" für die
    Fälligkeits-Erinnerung hinterlegte Adresse) - eine eigene Kontakt-E-Mail
    fürs Setup einzuführen wäre für diesen Einzelnutzer-Fall unnötig.
    """
    settings = get_settings(db)
    if not settings.reminder_email:
        return False, (
            "Keine Erinnerungs-E-Mail in den Einstellungen hinterlegt - Reset per Mail "
            "nicht möglich. Bitte per CLI zurücksetzen (siehe README, scripts/reset_password.py)."
        )
    if not settings.smtp_configured:
        return False, (
            "SMTP ist nicht konfiguriert - Reset per Mail nicht möglich. "
            "Bitte per CLI zurücksetzen (siehe README, scripts/reset_password.py)."
        )

    now = datetime.utcnow()
    token_valid = (
        settings.password_reset_token
        and settings.password_reset_token_expires_at
        and settings.password_reset_token_expires_at > now
    )
    if not token_valid:
        settings.password_reset_token = secrets.token_urlsafe(32)
        settings.password_reset_token_expires_at = now + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
        db.commit()

    link = f"{reset_url_base.rstrip('/')}/reset-password?token={settings.password_reset_token}"
    body = (
        "Ein Passwort-Reset für Rechnungsworkflow wurde angefordert.\n\n"
        f"Link zum Zurücksetzen (gültig {RESET_TOKEN_TTL_MINUTES} Minuten):\n{link}\n\n"
        "Wenn diese Anfrage nicht von Ihnen kam, kann sie ignoriert werden."
    )

    try:
        send_email(db, to=settings.reminder_email, subject="Passwort zurücksetzen – Rechnungsworkflow", body=body)
    except SmtpNotConfigured:
        return False, "SMTP ist nicht konfiguriert."
    except (smtplib.SMTPException, OSError):
        logger.warning("Versand des Passwort-Reset-Links fehlgeschlagen", exc_info=True)
        return False, (
            "Versand fehlgeschlagen. Bitte SMTP-Einstellungen prüfen oder "
            "per CLI zurücksetzen (siehe README, scripts/reset_password.py)."
        )

    return True, f"Link zum Zurücksetzen wurde an {settings.reminder_email} gesendet."


def validate_token(db: Session, token: str) -> bool:
    settings = get_settings(db)
    if not token or not settings.password_reset_token:
        return False
    if not secrets.compare_digest(settings.password_reset_token, token):
        return False
    if not settings.password_reset_token_expires_at or settings.password_reset_token_expires_at <= datetime.utcnow():
        return False
    return True


def complete_reset(db: Session, token: str, new_password: str) -> bool:
    if not validate_token(db, token):
        return False

    settings = get_settings(db)
    settings.admin_password_hash = hash_password(new_password)
    settings.password_reset_token = None
    settings.password_reset_token_expires_at = None
    db.commit()
    return True
